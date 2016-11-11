#!/bin/bash

set -xe

cd dracut/test
make V=1 SKIP="70" check
exit $?
