// SPDX-License-Identifier: MIT
// UniFi's documented-by-classfile JNI surface, backed by native libdatachannel.
// Authentication and authorization remain entirely in the unmodified vendor JVM.
#include <jni.h>
#include <rtc/rtc.h>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <deque>
#include <fstream>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {
JavaVM *vm;
jclass manager;
std::mutex registryMutex;
std::atomic<long long> nextOperation{1};
struct Transfer {
    jlong operation, channel, offset, length;
    std::vector<char> head, tail;
    std::string file;
    std::atomic<bool> cancelled{false};
};
struct Peer {
    int id, format, bootstrap = -1;
    std::atomic<bool> closed{false}, sdpSent{false}, connected{false};
    std::mutex mutex;
    std::condition_variable changed;
    std::map<int, std::string> channels;
    std::map<jlong, std::shared_ptr<Transfer>> transfers;
    std::deque<std::shared_ptr<Transfer>> queue;
    std::thread worker;
    std::chrono::steady_clock::time_point started = std::chrono::steady_clock::now();
};
std::map<int, std::shared_ptr<Peer>> peers;

// Each native callback uses its own JNIEnv; attached threads are JVM daemons.
struct Env {
    JNIEnv *env = nullptr;
    bool attached = false;
    Env() {
        if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_8) == JNI_EDETACHED)
            attached = vm->AttachCurrentThreadAsDaemon(reinterpret_cast<void **>(&env), nullptr) == JNI_OK;
        if (env) env->PushLocalFrame(32);
    }
    ~Env() {
        if (env) {
            if (env->ExceptionCheck()) {
                // Never print the exception: vendor messages can include session state.
                env->ExceptionClear();
                std::fprintf(stderr, "riscv-webrtc: Java callback failed\n");
            }
            env->PopLocalFrame(nullptr);
        }
        if (attached) vm->DetachCurrentThread();
    }
};
std::shared_ptr<Peer> peer(jlong id) {
    if (id <= 0 || id > INT32_MAX) return {};
    std::lock_guard<std::mutex> lock(registryMutex);
    auto it = peers.find(static_cast<int>(id));
    return it == peers.end() ? nullptr : it->second;
}
std::string text(JNIEnv *env, jstring value) {
    if (!value) return {};
    const char *p = env->GetStringUTFChars(value, nullptr);
    if (!p) return {};
    std::string result(p);
    env->ReleaseStringUTFChars(value, p);
    return result;
}
jstring str(JNIEnv *env, const std::string &s) { return env->NewStringUTF(s.c_str()); }
void signalError(const char *name, int id, jlong code, const char *message) {
    Env e;
    if (!e.env) return;
    auto method = e.env->GetStaticMethodID(manager, name, "(JJLjava/lang/String;)V");
    if (method) e.env->CallStaticVoidMethod(manager, method, jlong(id), code, str(e.env, message));
}
std::string label(const std::shared_ptr<Peer> &p, int channel) {
    std::lock_guard<std::mutex> lock(p->mutex);
    auto it = p->channels.find(channel);
    return it == p->channels.end() ? std::string() : it->second;
}
bool owns(const std::shared_ptr<Peer> &p, jlong channel) {
    if (!p || p->closed || channel <= 0 || channel > INT32_MAX) return false;
    std::lock_guard<std::mutex> lock(p->mutex);
    return p->channels.count(static_cast<int>(channel));
}
void channelEvent(const char *name, const std::shared_ptr<Peer> &p, int channel) {
    Env e;
    if (!e.env) return;
    auto method = e.env->GetStaticMethodID(manager, name, "(JLjava/lang/String;J)V");
    if (method) e.env->CallStaticVoidMethod(manager, method, jlong(p->id), str(e.env, label(p, channel)), jlong(channel));
}
void opened(int channel, void *context) {
    auto p = peer(reinterpret_cast<intptr_t>(context));
    if (p && !p->closed) channelEvent("signalDataChannelCreated", p, channel);
}
void channelClosed(int channel, void *context) {
    auto p = peer(reinterpret_cast<intptr_t>(context));
    if (p && !p->closed) channelEvent("signalDataChannelClosed", p, channel);
}
void channelError(int channel, const char *, void *context) {
    auto p = peer(reinterpret_cast<intptr_t>(context));
    if (!p || p->closed) return;
    Env e;
    if (!e.env) return;
    auto method = e.env->GetStaticMethodID(manager, "signalDataChannelCreateError", "(JLjava/lang/String;JLjava/lang/String;)V");
    if (method) e.env->CallStaticVoidMethod(manager, method, jlong(p->id), str(e.env, label(p, channel)), jlong(-2), str(e.env, "Native data channel failed"));
}
// UniFi's upload bridge calls ContentType.parse(null/"") and then FileBody,
// which throws for browser File objects with no registered MIME type (.unf).
// Supply the standard binary MIME type only for those backup-upload envelopes.
// The operation ID, binary body, authentication fields and all other requests
// remain unchanged. Each chunk carries the same envelope in this protocol.
std::vector<char> backupMime(const char *message, size_t size) {
    if (size < 18) return {};
    auto read32 = [](const char *p) {
        return (uint32_t(uint8_t(p[0])) << 24) | (uint32_t(uint8_t(p[1])) << 16)
             | (uint32_t(uint8_t(p[2])) << 8) | uint32_t(uint8_t(p[3]));
    };
    uint32_t length = read32(message), headerLength = read32(message + 12);
    if (headerLength < 2 || headerLength > 65536 || headerLength > size - 16 || length < headerLength + 12) return {};
    auto header = nlohmann::ordered_json::parse(message + 16, message + 16 + headerLength, nullptr, false);
    if (!header.is_object() || !header.contains("path") || header["path"] != "/upload/backup"
        || !header.contains("filename") || !header["filename"].is_string()) return {};
    auto filename = header["filename"].get<std::string>();
    if (filename.size() < 4 || filename.substr(filename.size() - 4) != ".unf") return {};
    if (header.contains("contentType") && !header["contentType"].is_null()) {
        if (!header["contentType"].is_string()) return {};
        auto value = header["contentType"].get<std::string>();
        if (value.find_first_not_of(" \t\r\n") != std::string::npos) return {};
    }
    header["contentType"] = "application/octet-stream";
    auto encoded = header.dump();
    int64_t delta = int64_t(encoded.size()) - headerLength;
    if (int64_t(length) + delta > INT32_MAX || int64_t(size) + delta > INT32_MAX) return {};
    std::vector<char> result;
    result.reserve(size_t(int64_t(size) + delta));
    result.insert(result.end(), message, message + 16);
    result.insert(result.end(), encoded.begin(), encoded.end());
    result.insert(result.end(), message + 16 + headerLength, message + size);
    auto write32 = [&](size_t at, uint32_t value) {
        for (int i = 0; i < 4; ++i) result[at + i] = char(value >> (24 - 8 * i));
    };
    write32(0, uint32_t(int64_t(length) + delta));
    write32(12, uint32_t(encoded.size()));
    return result;
}
void received(int channel, const char *message, int size, void *context) {
    auto p = peer(reinterpret_cast<intptr_t>(context));
    if (!p || p->closed) return;
    if (size < 0) size = static_cast<int>(std::strlen(message));
    std::vector<char> normalized;
    try { normalized = backupMime(message, size_t(size)); }
    catch (...) { /* Leave malformed/unknown payloads to the vendor parser. */ }
    if (!normalized.empty()) {
        message = normalized.data();
        size = int(normalized.size());
    }
    Env e;
    if (!e.env) return;
    auto bytes = e.env->NewByteArray(size);
    if (!bytes) return;
    e.env->SetByteArrayRegion(bytes, 0, size, reinterpret_cast<const jbyte *>(message));
    auto method = e.env->GetStaticMethodID(manager, "signalDataChannelInput", "(JLjava/lang/String;J[B)V");
    if (method) e.env->CallStaticVoidMethod(manager, method, jlong(p->id), str(e.env, label(p, channel)), jlong(channel), bytes);
}
void setupChannel(const std::shared_ptr<Peer> &p, int channel) {
    char name[4096] = {};
    if (rtcGetDataChannelLabel(channel, name, sizeof(name)) < 0) return;
    {
        std::lock_guard<std::mutex> lock(p->mutex);
        p->channels[channel] = name;
    }
    rtcSetUserPointer(channel, reinterpret_cast<void *>(intptr_t(p->id)));
    rtcSetOpenCallback(channel, opened);
    rtcSetClosedCallback(channel, channelClosed);
    rtcSetErrorCallback(channel, channelError);
    rtcSetMessageCallback(channel, received);
}
void incoming(int id, int channel, void *) {
    auto p = peer(id);
    if (p && !p->closed) setupChannel(p, channel);
}
std::string description(int id) {
    int size = rtcGetLocalDescription(id, nullptr, 0);
    if (size <= 0 || size > 1024 * 1024) return {};
    std::vector<char> data(size);
    if (rtcGetLocalDescription(id, data.data(), size) < 0) return {};
    return data.data();
}
void gathering(int id, rtcGatheringState state, void *) {
    auto p = peer(id);
    if (!p || p->closed || state != RTC_GATHERING_COMPLETE || p->sdpSent.exchange(true)) return;
    auto sdp = description(id);
    if (sdp.empty()) { signalError("signalSDPError", id, -2, "No local SDP"); return; }
    bool relay = sdp.find(" typ relay") != std::string::npos;
    // Modern SCTP SDP is interoperable with Site Manager. Report the actual format.
    Env e;
    if (!e.env) return;
    auto method = e.env->GetStaticMethodID(manager, "signalSDPReady", "(JLjava/lang/String;IZZ)V");
    if (method) e.env->CallStaticVoidMethod(manager, method, jlong(id), str(e.env, sdp), jint(1), JNI_TRUE, jboolean(relay));
    std::fprintf(stderr, "riscv-webrtc: ICE gathering complete; relay=%s\n", relay ? "yes" : "no");
}
void stateChanged(int id, rtcState state, void *) {
    auto p = peer(id);
    if (!p || p->closed) return;
    std::fprintf(stderr, "riscv-webrtc: transport state=%d\n", int(state));
    if (state == RTC_CONNECTED) {
        p->connected = true;
        char local[512] = {}, remote[512] = {}, lc[4096] = {}, rc[4096] = {};
        rtcGetLocalAddress(id, local, sizeof(local));
        rtcGetRemoteAddress(id, remote, sizeof(remote));
        rtcGetSelectedCandidatePair(id, lc, sizeof(lc), rc, sizeof(rc));
        auto split = [](const std::string &address) {
            auto pos = address.rfind(':');
            if (pos == std::string::npos) return std::make_pair(address, jlong(0));
            jlong port = 0;
            try { port = std::stoll(address.substr(pos + 1)); } catch (...) {}
            return std::make_pair(address.substr(0, pos), port);
        };
        auto l = split(local), r = split(remote);
        Env e;
        if (!e.env) return;
        auto method = e.env->GetStaticMethodID(manager, "signalConnectionSucceeded", "(JLjava/lang/String;JLjava/lang/String;JZZJ)V");
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - p->started).count();
        if (method) e.env->CallStaticVoidMethod(manager, method, jlong(id), str(e.env, l.first), l.second,
            str(e.env, r.first), r.second, jboolean(std::strstr(lc, " typ relay") != nullptr),
            jboolean(std::strstr(rc, " typ relay") != nullptr), jlong(ms));
    } else if (state == RTC_FAILED) {
        signalError(p->connected ? "signalConnectionTerminated" : "signalConnectionFailed", id, -2, "ICE/DTLS/SCTP transport failed");
    } else if (state == RTC_DISCONNECTED || state == RTC_CLOSED) {
        signalError("signalConnectionTerminated", id, -3, "Remote transport disconnected");
    }
}
// Libdatachannel's raw logger can contain authenticated TURN URIs and SDP.
// Emit only fixed, non-sensitive state events above.
void quietLog(rtcLogLevel, const char *) {}
void transferResult(const std::shared_ptr<Peer> &p, const Transfer &t, bool success, jlong bytes, jlong duration) {
    Env e;
    if (!e.env) return;
    const char *name = success ? "signalSendFileSucceeded" : "signalSendFileFailed";
    const char *signature = success ? "(JJJLjava/lang/String;JJJ)V" : "(JJJLjava/lang/String;JJJLjava/lang/String;)V";
    auto method = e.env->GetStaticMethodID(manager, name, signature);
    if (!method) return;
    if (success) e.env->CallStaticVoidMethod(manager, method, jlong(p->id), t.channel, t.operation, str(e.env, t.file), t.offset, bytes, duration);
    else e.env->CallStaticVoidMethod(manager, method, jlong(p->id), t.channel, t.operation, str(e.env, t.file), t.offset, bytes, jlong(-2), str(e.env, "Transfer failed or cancelled"));
}
void transfers(const std::shared_ptr<Peer> &p) {
    for (;;) {
        std::shared_ptr<Transfer> t;
        {
            std::unique_lock<std::mutex> lock(p->mutex);
            p->changed.wait(lock, [&] { return p->closed || !p->queue.empty(); });
            if (p->closed) return;
            t = p->queue.front();
            p->queue.pop_front();
        }
        auto start = std::chrono::steady_clock::now();
        jlong sent = 0;
        auto send = [&](const char *data, size_t count) {
            while (count) {
                if (p->closed || t->cancelled || !rtcIsOpen(int(t->channel))) return false;
                while (rtcGetBufferedAmount(int(t->channel)) > 1024 * 1024) {
                    if (p->closed || t->cancelled || std::chrono::steady_clock::now() - start > std::chrono::seconds(120)) return false;
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                }
                // Conservative size works with the vendor/browser SCTP message limits.
                auto chunk = std::min(count, size_t(16384));
                if (rtcSendMessage(int(t->channel), data, int(chunk)) < 0) return false;
                data += chunk; count -= chunk; sent += chunk;
            }
            return true;
        };
        bool ok = send(t->head.data(), t->head.size());
        if (ok && !t->file.empty()) {
            std::ifstream file(t->file, std::ios::binary);
            if (!file || t->offset < 0) ok = false;
            else {
                file.seekg(t->offset);
                jlong remaining = t->length;
                char buffer[16384];
                while (ok && (remaining < 0 || remaining > 0)) {
                    auto n = remaining < 0 ? sizeof(buffer) : std::min(size_t(remaining), sizeof(buffer));
                    file.read(buffer, std::streamsize(n));
                    auto got = file.gcount();
                    if (!got) { if (remaining > 0 || !file.eof()) ok = false; break; }
                    ok = send(buffer, size_t(got));
                    if (remaining > 0) remaining -= got;
                }
            }
        }
        if (ok) ok = send(t->tail.data(), t->tail.size());
        if (!p->closed) transferResult(p, *t, ok, sent,
            std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count());
        std::lock_guard<std::mutex> lock(p->mutex);
        p->transfers.erase(t->operation);
    }
}
void closePeer(const std::shared_ptr<Peer> &p) {
    if (!p || p->closed.exchange(true)) return;
    p->changed.notify_all();
    if (p->worker.joinable()) p->worker.join();
    rtcClosePeerConnection(p->id);
    std::vector<int> channels;
    {
        std::lock_guard<std::mutex> lock(p->mutex);
        for (const auto &entry : p->channels) channels.push_back(entry.first);
    }
    for (int channel : channels) rtcDeleteDataChannel(channel);
    if (p->bootstrap >= 0) rtcDeleteDataChannel(p->bootstrap);
    rtcDeletePeerConnection(p->id);
    {
        std::lock_guard<std::mutex> lock(registryMutex);
        peers.erase(p->id);
    }
    Env e;
    if (!e.env) return;
    auto method = e.env->GetStaticMethodID(manager, "signalConnectionTeardown", "(J)V");
    if (method) e.env->CallStaticVoidMethod(manager, method, jlong(p->id));
}
std::string encoded(const std::string &value) {
    static const char hex[] = "0123456789ABCDEF";
    std::string out;
    for (unsigned char c : value) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '~') out += c;
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}
bool byteRange(JNIEnv *env, jbyteArray data, jint offset, jint count, std::vector<char> &out) {
    if (!data) return count <= 0;
    jsize size = env->GetArrayLength(data);
    if (offset < 0 || offset > size) return false;
    if (count == -1) count = size - offset;
    if (count < 0 || count > size - offset) return false;
    out.resize(count);
    if (count) env->GetByteArrayRegion(data, offset, count, reinterpret_cast<jbyte *>(out.data()));
    return !env->ExceptionCheck();
}
}

extern "C" {
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *jvm, void *) {
    vm = jvm;
    JNIEnv *env;
    if (vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_8) != JNI_OK) return JNI_ERR;
    auto local = env->FindClass("com/ubnt/webrtc/WebRTCManager");
    if (!local) return JNI_ERR;
    manager = static_cast<jclass>(env->NewGlobalRef(local));
    env->DeleteLocalRef(local);
    rtcInitLogger(RTC_LOG_NONE, quietLog);
    return JNI_VERSION_1_8;
}
JNIEXPORT jstring JNICALL Java_com_ubnt_webrtc_WebRTCManager_version(JNIEnv *env, jclass, jboolean) {
    return str(env, "unifi-riscv native WebRTC adapter / libdatachannel " RTC_VERSION);
}
JNIEXPORT void JNICALL Java_com_ubnt_webrtc_WebRTCManager_activateInternalLogging(JNIEnv *, jclass, jboolean) {}
JNIEXPORT jstring JNICALL Java_com_ubnt_webrtc_WebRTCManager_getErrorDescription(JNIEnv *env, jclass, jlong code) {
    return str(env, code == 0 ? "Success" : "Native WebRTC operation failed");
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_createWebRTC(JNIEnv *env, jclass, jstring stun, jstring turn, jstring user, jstring password, jint format) {
    std::vector<std::string> servers;
    auto s = text(env, stun), t = text(env, turn);
    // Endpoint-only diagnostics: credentials and SDP are never logged.
    auto logEndpoint = [](const char *kind, std::string endpoint) {
        auto at = endpoint.rfind('@');
        if (at != std::string::npos) endpoint = endpoint.substr(at + 1);
        if (endpoint.size() < 256 && endpoint.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:[]?=_/") == std::string::npos)
            std::fprintf(stderr, "riscv-webrtc: %s endpoint=%s\n", kind, endpoint.c_str());
    };
    logEndpoint("STUN", s);
    logEndpoint("TURN", t);
    if (!s.empty()) servers.push_back(s.find("stun:") == 0 ? s : "stun:" + s);
    if (!t.empty()) {
        if (t.find("turn:") != 0 && t.find("turns:") != 0) t = "turn:" + t;
        auto colon = t.find(':') + 1;
        while (colon < t.size() && t[colon] == '/') ++colon;
        t.insert(colon, encoded(text(env, user)) + ":" + encoded(text(env, password)) + "@");
        servers.push_back(t);
    }
    std::vector<const char *> pointers;
    for (const auto &server : servers) pointers.push_back(server.c_str());
    rtcConfiguration config{};
    config.iceServers = pointers.data();
    config.iceServersCount = int(pointers.size());
    config.disableAutoNegotiation = true;
    config.maxMessageSize = 16 * 1024 * 1024;
    int id = rtcCreatePeerConnection(&config);
    if (id < 0) return id;
    auto p = std::make_shared<Peer>();
    p->id = id; p->format = format;
    {
        std::lock_guard<std::mutex> lock(registryMutex);
        peers[id] = p;
    }
    rtcSetStateChangeCallback(id, stateChanged);
    rtcSetGatheringStateChangeCallback(id, gathering);
    rtcSetDataChannelCallback(id, incoming);
    p->worker = std::thread(transfers, p);
    std::fprintf(stderr, "riscv-webrtc: peer created; ICE servers=%zu\n", servers.size());
    return id;
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_startCreateSDPOffer(JNIEnv *, jclass, jlong id) {
    auto p = peer(id);
    if (!p || p->closed) return -1;
    // A negotiated channel adds SCTP to the offer without sending a DCEP request.
    rtcDataChannelInit init{};
    init.negotiated = true; init.manualStream = true; init.stream = 1022;
    p->bootstrap = rtcCreateDataChannelEx(p->id, "riscv-sctp-bootstrap", &init);
    if (p->bootstrap < 0) return p->bootstrap;
    return rtcSetLocalDescription(p->id, "offer");
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_startCreateSDPAnswer(JNIEnv *env, jclass, jlong id, jstring sdp) {
    auto p = peer(id);
    if (!p || p->closed || !sdp) return -1;
    int rc = rtcSetRemoteDescription(p->id, text(env, sdp).c_str(), "offer");
    return rc < 0 ? rc : rtcSetLocalDescription(p->id, "answer");
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_receiveSDPAnswer(JNIEnv *env, jclass, jlong id, jstring sdp, jlong) {
    auto p = peer(id);
    return !p || p->closed || !sdp ? -1 : rtcSetRemoteDescription(p->id, text(env, sdp).c_str(), "answer");
}
JNIEXPORT void JNICALL Java_com_ubnt_webrtc_WebRTCManager_close(JNIEnv *, jclass, jlong id) { closePeer(peer(id)); }
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_createDataChannel(JNIEnv *env, jclass, jlong id, jstring name) {
    auto p = peer(id);
    if (!p || p->closed || !name) return -1;
    int channel = rtcCreateDataChannel(p->id, text(env, name).c_str());
    if (channel >= 0) setupChannel(p, channel);
    return channel;
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_closeDataChannel(JNIEnv *, jclass, jlong id, jlong channel) {
    auto p = peer(id);
    return owns(p, channel) ? rtcClose(int(channel)) : -1;
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_sendData(JNIEnv *env, jclass, jlong id, jlong channel, jbyteArray data, jlong offset, jlong count) {
    auto p = peer(id);
    if (!owns(p, channel) || offset < 0 || offset > INT32_MAX || count < 0 || count > INT32_MAX) return -1;
    std::vector<char> bytes;
    if (!byteRange(env, data, jint(offset), jint(count), bytes)) return -1;
    return rtcSendMessage(int(channel), bytes.data(), int(bytes.size()));
}
JNIEXPORT jlong JNICALL Java_com_ubnt_webrtc_WebRTCManager_sendFile(JNIEnv *env, jclass, jlong id, jlong channel, jbyteArray head, jint ho, jint hl, jstring file, jlong offset, jlong length, jbyteArray tail, jint to, jint tl) {
    auto p = peer(id);
    if (!owns(p, channel) || offset < 0 || length < -1) return -1;
    auto t = std::make_shared<Transfer>();
    t->operation = nextOperation++; t->channel = channel; t->offset = offset; t->length = length;
    t->file = text(env, file);
    if (!byteRange(env, head, ho, hl, t->head) || !byteRange(env, tail, to, tl, t->tail)) return -1;
    {
        std::lock_guard<std::mutex> lock(p->mutex);
        if (p->closed || p->transfers.size() >= 256) return -3;
        p->transfers[t->operation] = t;
        p->queue.push_back(t);
    }
    p->changed.notify_one();
    return t->operation;
}
JNIEXPORT void JNICALL Java_com_ubnt_webrtc_WebRTCManager_cancelSendFile(JNIEnv *, jclass, jlong id, jlong operation) {
    auto p = peer(id);
    if (!p) return;
    std::lock_guard<std::mutex> lock(p->mutex);
    auto it = p->transfers.find(operation);
    if (it != p->transfers.end()) it->second->cancelled = true;
}
JNIEXPORT void JNICALL Java_com_ubnt_webrtc_WebRTCManager_mdnsResolved(JNIEnv *env, jclass, jlong id, jstring candidate, jstring address) {
    auto p = peer(id);
    if (!p || p->closed) return;
    auto c = text(env, candidate), a = text(env, address);
    // Replace only the mDNS hostname token; never rewrite the rest of the candidate.
    auto end = c.find(".local");
    if (end != std::string::npos && !a.empty()) {
        auto begin = c.rfind(' ', end);
        if (begin != std::string::npos) c.replace(begin + 1, end + 6 - begin - 1, a);
        rtcAddRemoteCandidate(p->id, c.c_str(), "0");
    }
}
JNIEXPORT void JNICALL Java_com_ubnt_webrtc_WebRTCManager_tearDownInternal(JNIEnv *, jclass) {
    std::vector<std::shared_ptr<Peer>> all;
    {
        std::lock_guard<std::mutex> lock(registryMutex);
        for (const auto &entry : peers) all.push_back(entry.second);
    }
    for (const auto &p : all) closePeer(p);
}
}
