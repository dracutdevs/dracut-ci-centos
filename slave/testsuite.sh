#!/bin/bash

set -xe

cd dracut

./configure --disable-documentation

cd test
make V=1 check
exit $?
