// SPDX-License-Identifier: MIT
// Uses the real, unmodified UniFi JNI declarations and observer interface.
import com.ubnt.webrtc.WebRTCManager;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class NativeWebRTCProbe {
    public static void main(String[] args) throws Exception {
        System.load(args[0]);
        boolean rejectFingerprint = args.length > 1 && args[1].equals("reject-fingerprint");
        boolean uploadEnvelope = args.length > 1 && args[1].equals("upload-envelope");
        boolean otherEnvelope = args.length > 1 && args[1].equals("non-upload-envelope");
        Class<?> observer = Arrays.stream(WebRTCManager.class.getMethods())
            .filter(m -> m.getName().equals("setObserver")).findFirst().orElseThrow().getParameterTypes()[0];
        AtomicLong offerer = new AtomicLong(), answerer = new AtomicLong();
        CountDownLatch connected = new CountDownLatch(2), delivered = new CountDownLatch(2);
        CountDownLatch rejected = new CountDownLatch(1);
        AtomicReference<Throwable> callbackFailure = new AtomicReference<>();
        byte[] body = "native-riscv-ice-dtls-sctp-probe".getBytes(StandardCharsets.UTF_8);
        String headerText = "{\"path\":\"" + (uploadEnvelope ? "/upload/backup" : "/api/s/default/test")
            + "\",\"filename\":\"probe.unf\",\"contentType\":\"\",\"authorization\":\"synthetic-test-only\"}";
        byte[] header = headerText.getBytes(StandardCharsets.UTF_8);
        byte[] payload = uploadEnvelope || otherEnvelope
            ? ByteBuffer.allocate(16 + header.length + body.length).putInt(12 + header.length + body.length)
                .putLong(23).putInt(header.length).put(header).put(body).array()
            : body;
        Object proxy = Proxy.newProxyInstance(observer.getClassLoader(), new Class<?>[]{observer}, (object, method, values) -> {
            try {
            Class<?>[] t = method.getParameterTypes();
            if (t.length == 5 && t[1] == String.class && t[2] == int.class) {
                long id = (Long)values[0];
                String sdp = (String)values[1];
                if (rejectFingerprint && id == offerer.get())
                    sdp = sdp.replaceAll("(?m)^a=fingerprint:[^\\r\\n]+", "a=fingerprint:sha-256 " + "00:".repeat(31) + "00");
                long rc = id == offerer.get()
                    ? WebRTCManager.startCreateSDPAnswer(answerer.get(), sdp)
                    : WebRTCManager.receiveSDPAnswer(offerer.get(), sdp, 0);
                if (rc != 0) throw new AssertionError("SDP rejected: " + rc);
            } else if (t.length == 8 && t[1] == String.class) {
                connected.countDown();
            } else if (t.length == 3 && t[1] == String.class && t[2] == long.class) {
                // Each side sends through the opened, genuine SCTP data channel.
                WebRTCManager.enqueueData((Long)values[0], (Long)values[2], payload, 0, payload.length);
            } else if (t.length == 4 && t[3] == byte[].class) {
                byte[] actual = (byte[])values[3];
                if (uploadEnvelope) {
                    ByteBuffer frame = ByteBuffer.wrap(actual);
                    if (frame.getInt() != actual.length - 4 || frame.getLong() != 23)
                        throw new AssertionError("Upload frame ID/length changed incorrectly");
                    int size = frame.getInt();
                    byte[] metadata = new byte[size]; frame.get(metadata);
                    String text = new String(metadata, StandardCharsets.UTF_8);
                    if (!text.contains("\"contentType\":\"application/octet-stream\"")
                        || !text.contains("\"authorization\":\"synthetic-test-only\""))
                        throw new AssertionError("MIME fallback or authorization preservation failed");
                    byte[] data = new byte[frame.remaining()]; frame.get(data);
                    if (!Arrays.equals(body, data)) throw new AssertionError("Upload body changed");
                } else if (!Arrays.equals(payload, actual)) throw new AssertionError("Payload corruption");
                delivered.countDown();
            } else if (t.length == 3 && t[1] == long.class && t[2] == String.class) {
                if (rejectFingerprint) rejected.countDown();
                else throw new AssertionError("Native transport error " + values[1]);
            }
            } catch (Throwable failure) { callbackFailure.set(failure); }
            return method.getReturnType() == boolean.class ? true : null;
        });
        WebRTCManager.class.getMethod("setObserver", observer).invoke(null, proxy);
        try {
            offerer.set(WebRTCManager.createWebRTC(null, null, null, null, 1));
            answerer.set(WebRTCManager.createWebRTC(null, null, null, null, 1));
            if (offerer.get() <= 0 || answerer.get() <= 0) throw new AssertionError("Peer creation failed");
            if (WebRTCManager.startCreateSDPOffer(offerer.get()) != 0) throw new AssertionError("Offer failed");
            if (rejectFingerprint) {
                if (!rejected.await(35, TimeUnit.SECONDS) || connected.getCount() == 0)
                    throw new AssertionError("Altered DTLS fingerprint was not rejected");
                if (callbackFailure.get() != null) throw new AssertionError(callbackFailure.get());
                System.out.println("PASS: altered DTLS fingerprint rejected; authentication checks active");
                return;
            }
            if (!connected.await(30, TimeUnit.SECONDS)) throw new AssertionError("ICE/DTLS connection timeout");
            if (WebRTCManager.createDataChannel(offerer.get(), "riscv-probe") <= 0) throw new AssertionError("Channel failed");
            if (!delivered.await(30, TimeUnit.SECONDS)) throw new AssertionError("Bidirectional data timeout");
            if (callbackFailure.get() != null) throw new AssertionError(callbackFailure.get());
            if (WebRTCManager.sendData(offerer.get(), Long.MAX_VALUE, payload, 0, payload.length) >= 0)
                throw new AssertionError("Invalid channel accepted");
            System.out.println("PASS: vendor JNI ABI, ICE, verified DTLS, SCTP and bidirectional data on native riscv64");
            if (uploadEnvelope) System.out.println("PASS: backup MIME fallback preserves operation ID, authorization and file bytes");
            if (otherEnvelope) System.out.println("PASS: non-upload request is byte-for-byte unchanged");
        } finally {
            WebRTCManager.close(offerer.get());
            WebRTCManager.close(answerer.get());
            WebRTCManager.tearDown();
        }
    }
}
