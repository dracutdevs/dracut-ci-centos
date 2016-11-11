#!/bin/bash

set -xe

if [[ $TESTS == rpm ]]; then
    make rpm
    exit $?
fi

cd dracut/test
make V=1 SKIP="70" check
exit $?
