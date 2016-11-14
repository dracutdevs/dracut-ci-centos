#!/usr/bin/python

# GPLv2 etc.

import os, json, urllib, subprocess, sys, argparse, fcntl, time

github_base = "https://github.com/dracutdevs/"
git_name = "dracut-ci-centos"

debug = False
reboot_count = 0

def dprint(msg):
	global debug

	if debug:
		print "Debug:: " + msg

def duffy_cmd(cmd, params):
	url_base = "http://admin.ci.centos.org:8080"
	url = "%s%s?%s" % (url_base, cmd, urllib.urlencode(params))
	dprint("Duffy API url = " + url)
	for i in xrange(1,10):
                try:
                        ret = urllib.urlopen(url).read()
                except IOError:
                        continue
                return ret
        raise IOError

def host_done(key, ssid):
	params = { "key": key, "ssid": ssid }
	duffy_cmd("/Node/done", params)
	print "Duffy: Host with ssid %s marked as done" % ssid

def exec_cmd(cmd):
	dprint("Executing command: '%s'" % ("' '".join(cmd)))

	p = subprocess.Popen(cmd, stdout = None, stderr = None, shell = False, bufsize = 1)
	p.communicate()
	p.wait()

	return p.returncode

def remote_exec(host, remote_cmd, port = 22, expected_ret = 0):
	cmd = [ '/usr/bin/ssh',
		'-t',
		'-o', 'UserKnownHostsFile=/dev/null',
		'-o', 'StrictHostKeyChecking=no',
		'-o', 'ConnectTimeout=180',
		'-o', 'TCPKeepAlive=yes',
		'-o', 'ServerAliveInterval=2',
                '-p', str(port),
		'-l', 'root',
		host, remote_cmd ]

	print(">>> Executing remote command: '%s' on %s port %d" % (remote_cmd, host, port))

	start = time.time()
	ret = exec_cmd(cmd)
	end = time.time()

	print("<<< Remote command finished after %.1f seconds, return code = %d" % (end - start, ret))

	if ret != expected_ret:
		raise Exception("Remote command returned code %d, expected %d. Bailing out." % (ret, expected_ret))

def remote_scp(src, dst, port = 22, expected_ret = 0):
	cmd = [ '/usr/bin/scp',
		'-o', 'UserKnownHostsFile=/dev/null',
		'-o', 'StrictHostKeyChecking=no',
		'-o', 'ConnectTimeout=180',
                '-P', str(port),
                src, dst ]

	print(">>> Copying: '%s' to %s port %d" % (src, dst, port))

	start = time.time()
	ret = exec_cmd(cmd)
	end = time.time()

	print("<<< Remote command finished after %.1f seconds, return code = %d" % (end - start, ret))

	if ret != expected_ret:
		raise Exception("Remote command returned code %d, expected %d. Bailing out." % (ret, expected_ret))

def remote_rsync(src, dst, expected_ret = 0):
	cmd = [ '/usr/bin/rsync', '-Pavor', src, dst ]

	print(">>> Copying: '%s' to %s" % (src, dst))

	start = time.time()
	ret = exec_cmd(cmd)
	end = time.time()

	print("<<< Command finished after %.1f seconds, return code = %d" % (end - start, ret))

	if ret != expected_ret:
		raise Exception("Command returned code %d, expected %d. Bailing out." % (ret, expected_ret))

def ping_host(host):
	cmd = [ '/usr/bin/ping', '-q', '-c', '1', '-W', '10', host ]
	print("Pinging host %s ..." % host)

	for i in range(20):
		ret = exec_cmd(cmd)
		if ret == 0:
			break;

	if ret != 0:
		raise Exception("Timeout waiting for ping")

	print("Host %s appears reachable again" % host)

def reboot_host(host):
	global reboot_count

	print("Rebooting host %s ..." % host)

	# the reboot command races against the graceful exit, so ignore the return code in this case
	remote_exec(host, "journalctl --no-pager -b && reboot", 255)

	time.sleep(60)
	ping_host(host)
	time.sleep(100)

	reboot_count += 1

def main():
	global debug
	global reboot_count

	parser = argparse.ArgumentParser()
	parser.add_argument('--ver',             help = 'CentOS version', default = '7')
	parser.add_argument('--arch',            help = 'Architecture', default = 'x86_64')
	parser.add_argument('--host',            help = 'Use an already provisioned build host')
	parser.add_argument('--pr',              help = 'Pull request ID to check out')
	parser.add_argument('--branch',          help = 'Commit/tag/branch to checkout')
	parser.add_argument('--keep',            help = 'Do not kill provisioned build host', action = 'store_const', const = True)
	parser.add_argument('--keep-on-failure', help = 'Do not kill provisioned build host unless all tests succeeded', action = 'store_const', const = True)
	parser.add_argument('--kill-host',       help = 'Mark a provisioned host as done and bail out')
	parser.add_argument('--kill-all-hosts',  help = 'Mark all provisioned hosts as done and bail out', action = 'store_const', const = True)
	parser.add_argument('--debug',           help = 'Enable debug output', action = 'store_const', const = True)
	args = parser.parse_args()

	key = open("%s/duffy.key" % os.environ.get("HOME", "."), "r").read().rstrip()

	debug = args.debug

	if args.kill_host:
		host_done(key, args.kill_host)
		return 0

	if args.kill_all_hosts:
		params = { "key": key }
		json_data = duffy_cmd("/Inventory", params)
		data = json.loads(json_data)

		for host in data:
			host_done(key, host[1])

		return 0

        if args.branch == "RHEL-6":
                args.ver = '6'

        if args.host:
		host = args.host
		ssid = None
	else:
		params = { "key": key, "ver": args.ver, "arch": args.arch }
                while True:
                        try:
		                json_data = duffy_cmd("/Node/get", params)
		                data = json.loads(json_data)
                        except ValueError:
                                continue
                        else:
                                break

		host = data['hosts'][0]
		ssid = data['ssid']

		print "Duffy: Host provisioning successful, hostname = %s, ssid = %s" % (host, ssid)

	ret = 0

	start = time.time()
	keep = args.keep

	try:
		if args.pr:
			sha = "pr:%s" % args.pr
		elif args.branch:
			sha = args.branch
		else:
			sha = ''

                if args.branch:
                        branch = args.branch
                else:
                        branch = ''

                if not branch.startswith("RHEL-"):
		        cmd = "yum install -y git rsyncd qemu-kvm ; printf '[srv]\\npath = /srv\\nread only = no\\n' > /etc/rsyncd.conf; systemctl start rsyncd; firewall-cmd --zone=public --add-port=873/tcp --permanent; firewall-cmd --reload;setenforce 0;chmod a+rwx /srv"
		        remote_exec(host, cmd)
                        remote_rsync("%s/F25CI.qcow2.gz" % os.environ.get("HOME", "."), "rsync://" + host + "/srv/")
		        cmd = "git clone %s%s.git && ./%s/slave/bootstrap.sh '%s' '%s'" % (github_base, git_name, git_name, sha, branch)
		        remote_exec(host, cmd)
                else:
		        cmd = "yum install -y git qemu-kvm && git clone %s%s.git && ./%s/slave/bootstrap.sh '%s' '%s'" % (github_base, git_name, git_name, sha, branch)
		        remote_exec(host, cmd)

		cmd = "TESTS='%s' %s/slave/testsuite.sh '%s'" % (os.environ.get("TESTS", ""), git_name, branch)

		remote_exec(host, cmd, port=(branch.startswith("RHEL-") and 22 or 22222))

		print("All tests succeeded.")

	except Exception as e:
		print("Execution failed! See logfile for details: %s" % str(e))
		ret = 255
		if args.keep_on_failure:
			keep = True

	finally:
		if ssid:
			if keep:
				print "Keeping host %s, ssid = %s" % (host, ssid)
			else:
				host_done(key, ssid);

		end = time.time()
		print("Total time %.1f seconds" % (end - start))

	sys.exit(ret)

if __name__ == "__main__":
	main()
