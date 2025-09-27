FROM pihole/pihole:latest
# Copy v6 safe assets
COPY scripts/speedtest.sh /usr/local/bin/pihole-speedtest
COPY web /var/www/html/speedtest
RUN mkdir -p /etc/pihole/speedtest &&         ln -sf /etc/pihole/speedtest/speedtest.json /var/www/html/speedtest/speedtest.json &&         chmod 0755 /usr/local/bin/pihole-speedtest
# Note: You still need a speedtest CLI in the image or on the host network namespace.
