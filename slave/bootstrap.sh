#!/bin/bash

set -xe

sha="$1"
branch="$2"

if grep -q -F vmx /proc/cpuinfo; then
    modprobe -r kvm_intel || :
    modprobe kvm_intel nested=1
elif grep -q -F svm /proc/cpuinfo; then
    modprobe -r kvm_amd || :
    modprobe kvm_amd nested=1
else
    exit 1
fi

(
    firewall-cmd --zone=public --add-port=22222/tcp --permanent
    firewall-cmd --reload
) &

if ! [[ $branch =~ RHEL-* ]] && ! fgrep -q Fedora /etc/redhat-release; then
    if [[ -f F25CI.qcow2.xz ]]; then
        gunzip F25CI.qcow2.gz &
    fi

    wait

    [[ -x /usr/bin/qemu ]] && BIN=/usr/bin/qemu && ARGS=""
    $(lsmod | grep -q '^kqemu ') && BIN=/usr/bin/qemu && ARGS="-kernel-kqemu "
    [[ -c /dev/kvm && -x /usr/bin/kvm ]] && BIN=/usr/bin/kvm && ARGS=""
    [[ -c /dev/kvm && -x /usr/bin/qemu-kvm ]] && BIN=/usr/bin/qemu-kvm && ARGS=""
    [[ -c /dev/kvm && -x /usr/libexec/qemu-kvm ]] && BIN=/usr/libexec/qemu-kvm && ARGS=""

    systemd-run $BIN $ARGS  \
        -drive format=qcow2,index=0,media=disk,file=/root/F25CI.qcow2 \
        -m 2048M \
        -smp $(nproc) \
        -no-reboot \
        -device e1000,netdev=user.0 \
        -nographic \
        -display none \
        -serial null \
        -cpu host \
        -netdev user,id=user.0,hostfwd=tcp::22222-:22 &

    for (( i=0; i < 60; i++ )); do
        ret=0
        ssh root@127.0.0.2 -p 22222 \
	    -o UserKnownHostsFile=/dev/null \
	    -o StrictHostKeyChecking=no \
	    -o ConnectTimeout=180 \
	    -o TCPKeepAlive=yes \
	    -o ServerAliveInterval=2 \
            "rm -fr dracut-ci-centos; git clone https://github.com/dracutdevs/dracut-ci-centos; ./dracut-ci-centos/slave/bootstrap.sh $sha $branch" \
            || ret=$?

        (( $ret != 255 )) && exit $ret
        sleep 1
    done
    exit 1
fi

[[ -d dracut ]] && rm -fr dracut

git clone ${branch:+-b "$branch"} https://github.com/dracutdevs/dracut.git

cd dracut

case "$sha" in
    pr:*)
	git fetch -fu origin refs/pull/${sha#pr:}/head:pr
	git checkout pr
	;;

    "")
	;;

    *)
	git checkout "$sha"
	;;
esac

if [[ $branch =~ RHEL-* ]]; then
     yum -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
     yum -y install $(<test/test-rpms.txt)
fi


exit 0
