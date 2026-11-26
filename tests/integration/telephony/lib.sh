#!/usr/bin/env bash
# Mira Voice — shared helpers for the softphone call tests (sourced, not run).
# baresip softphones that send a pure tone and record what they hear.
# shellcheck disable=SC2034 # pass/fail/DOMAIN are used by the scripts that source this file

MIRA_DIR=/opt/mira

pass=0 fail=0
ok() {
	echo "PASS  $*"
	pass=$((pass + 1))
}
bad() {
	echo "FAIL  $*"
	fail=$((fail + 1))
}

[ "$(id -u)" -eq 0 ] || {
	echo "run as root"
	exit 2
}
command -v baresip >/dev/null || {
	echo "baresip missing: sudo apt install baresip-core"
	exit 2
}

DOMAIN=$(sed -n 's/^MIRA_SIP_DOMAIN=//p' "$MIRA_DIR/.env" | tail -1)
LOCAL_IP=$(sed -n "s/^MIRA_LOCAL_IP=//p" "$MIRA_DIR/.env" | tail -1)

WORK=$(mktemp -d -p /var/tmp "mira-${TEST_NAME:-sip}-test.XXXXXX")
trap 'pkill -f "baresip -f $WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

# make_phone NAME SIP_PORT RTP_BASE TONE_HZ ACCOUNT_LINE [LISTEN_IP]
make_phone() {
	local dir="$WORK/$1"
	mkdir -p "$dir/rec"
	# 30 s sine tone, 8 kHz mono (baresip 1.0's ausine only runs at 48 kHz)
	python3 - "$dir/tone.wav" "$4" <<-'PY'
		import sys, wave, struct, math
		path, hz, rate = sys.argv[1], int(sys.argv[2]), 8000
		w = wave.open(path, "w"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
		w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(rate * 30)))
	PY
	cat >"$dir/config" <<-EOF
		poll_method		epoll
		sip_listen		${6:-$LOCAL_IP}:$2
		sip_cafile		$MIRA_DIR/config/tls/mira.crt
		rtp_ports		$3-$(($3 + 99))
		audio_source		aufile,$dir/tone.wav
		audio_player		aufile,$dir/rec/play.wav
		audio_alert		aufile,$dir/rec/alert.wav
		audio_channels		1
		snd_path		$dir/rec
		module_path		/usr/lib/baresip/modules
		module			g711.so
		module			aufile.so
		module			sndfile.so
		module			srtp.so
		module_app		account.so
		module_app		menu.so
	EOF
	printf '%s\n' "$5" >"$dir/accounts"
	: >"$dir/contacts"
}

declare -A PIDS
# baresip 1.0's own -t timer stops the phone but does not always exit the process, so
# every phone runs under `timeout` and is stopped and waited for before the next step.
run_phone() { # NAME SECONDS [COMMAND]
	local args=(-f "$WORK/$1")
	[ -n "${3:-}" ] && args+=(-e "$3")
	timeout --signal=TERM --kill-after=3 "$2" baresip "${args[@]}" >>"$WORK/$1/log.txt" 2>&1 &
	PIDS[$1]=$!
}
stop_phone() { # NAME
	[ -n "${PIDS[$1]:-}" ] || return 0
	kill "${PIDS[$1]}" 2>/dev/null
	wait "${PIDS[$1]}" 2>/dev/null
	unset "PIDS[$1]"
}

# dominant frequency and loudness of the received (decoded) audio
analyse() { # FILE
	python3 - "$1" <<-'PY'
		import sys, wave, struct, math
		# (<<- strips leading tabs: Python indentation inside is spaces)
		try:
		    w = wave.open(sys.argv[1]); n = w.getnframes(); rate = w.getframerate()
		    data = struct.unpack("<%dh" % n, w.readframes(n))
		except (wave.Error, EOFError, struct.error):
		    # phone killed before sndfile finished the WAV header: read the 16-bit 8 kHz
		    # samples that follow the 44-byte header directly
		    raw = open(sys.argv[1], "rb").read()[44:]; rate = 8000
		    data = struct.unpack("<%dh" % (len(raw) // 2), raw[: len(raw) // 2 * 2])
		data = data[-3 * rate:]  # last 3 s: after prompts (the echo test speaks first)
		if not data: print("0 0"); sys.exit()
		rms = math.sqrt(sum(x * x for x in data) / len(data))
		crossings = sum(1 for a, b in zip(data, data[1:]) if (a < 0) != (b < 0))
		print(int(rms), int(crossings / 2 / (len(data) / rate)))
	PY
}

# received file for a call: sndfile writes dump-<call>-dec.wav (decoded = what we heard)
received() { find "$WORK/$1/rec" -name '*-dec.wav' -size +2k | sort | tail -1; }

check_tone() { # NAME EXPECTED_HZ LABEL
	local f rms hz
	f=$(received "$1")
	if [ -z "$f" ]; then
		bad "$3: no audio recorded"
		return
	fi
	read -r rms hz < <(analyse "$f")
	if [ "$rms" -gt 500 ] && [ "$hz" -gt $(($2 * 85 / 100)) ] && [ "$hz" -lt $(($2 * 115 / 100)) ]; then
		ok "$3: heard ${hz} Hz (expected $2), level $rms"
	else
		bad "$3: heard ${hz} Hz level $rms (expected $2 Hz)"
	fi
}

registered() { # EXT
	docker exec mira-asterisk-1 asterisk -rx "pjsip show contacts" 2>/dev/null | grep -qE "Contact: +$1/"
}

# finish: print the result line, keep logs when something failed, exit non-zero on failure
finish() {
	echo
	echo "RESULT: $pass passed, $fail failed"
	if [ "$fail" -gt 0 ]; then
		echo "--- logs in $WORK kept for debugging"
		trap - EXIT
		tail -n 25 "$WORK"/*/log.txt
	fi
	[ "$fail" -eq 0 ]
}
