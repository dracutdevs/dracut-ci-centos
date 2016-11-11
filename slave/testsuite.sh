#!/bin/bash

set -xe

cd dracut

if [[ $TESTS == rpm ]]; then
    ./configure
    make rpm
    exit $?
fi

./configure --disable-documentation

cd test
make V=1 SKIP="70" check
exit $?
