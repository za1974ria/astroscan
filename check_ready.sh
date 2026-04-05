#!/bin/bash
for i in {1..15}
do
    sleep 1
    if curl -s http://127.0.0.1:5003/ready | grep '"ready":true'
    then
        echo "AstroScan READY"
        exit 0
    fi
done

echo "AstroScan NOT READY"
exit 1
