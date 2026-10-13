#!/bin/bash
set -euo pipefail
cd /opt/unifi-riscv/app/current
exec /usr/lib/jvm/java-25-openjdk-riscv64/bin/java \
    -Xms128M -Xmx512M -XX:+UseParallelGC \
    -Dlogback.configurationFile=/etc/unifi-riscv/logback.xml \
    -Dlogging.config=/etc/unifi-riscv/logback.xml \
    -Dfile.encoding=UTF-8 -Djava.awt.headless=true \
    -Dunifi.core.enabled=false -Dunifi.mongodb.service.enabled=false \
    -Djna.library.path=/usr/lib/riscv64-linux-gnu \
    -Dorg.xerial.snappy.use.systemlib=true \
    -XX:+ExitOnOutOfMemoryError -XX:ErrorFile=/var/log/unifi/jvm-crash.log \
    -Xlog:gc:/var/log/unifi/gc.log:time:filecount=2,filesize=5M \
    --add-opens java.base/java.lang=ALL-UNNAMED \
    --add-opens java.base/java.time=ALL-UNNAMED \
    --add-opens java.base/sun.security.util=ALL-UNNAMED \
    --add-opens java.base/java.io=ALL-UNNAMED \
    --add-opens java.rmi/sun.rmi.transport=ALL-UNNAMED \
    --enable-native-access=ALL-UNNAMED \
    -jar lib/ace.jar start
