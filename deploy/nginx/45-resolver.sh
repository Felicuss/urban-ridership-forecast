#!/bin/sh
set -eu

resolver="$(awk '$1 == "nameserver" { print $2; exit }' /etc/resolv.conf)"
test -n "$resolver"
sed -i "s/resolver 127\.0\.0\.11 valid=10s/resolver $resolver valid=10s/" /etc/nginx/conf.d/default.conf
