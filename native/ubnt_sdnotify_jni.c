// SPDX-License-Identifier: MIT
// Independently implemented compatibility bridge, 2026-10-13.
#include <errno.h>
#include <jni.h>
#include <systemd/sd-daemon.h>

JNIEXPORT jint JNICALL Java_com_ubnt_sdnotify_SDNotify_sdnotifyjni(
    JNIEnv *env, jclass klass, jint unset_environment, jstring state) {
    (void)klass;
    if (state == NULL) return -EINVAL;
    const char *value = (*env)->GetStringUTFChars(env, state, NULL);
    if (value == NULL) return -ENOMEM;
    int result = sd_notify(unset_environment, value);
    (*env)->ReleaseStringUTFChars(env, state, value);
    return result;
}
