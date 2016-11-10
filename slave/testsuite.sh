#!/bin/bash

set -xe

cd dracut/test
make V=1 check
