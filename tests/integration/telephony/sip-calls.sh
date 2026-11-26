#!/usr/bin/env bash
# Mira Voice — task 0.3 gate, softphone part. Two baresip softphones register through Kamailio
# (one over UDP with plain RTP, one over TLS with mandatory SRTP), call the echo test and each
# other, record what they hear, and the received audio is checked for the *other* side's tone:
#   phone A sends 440 Hz, phone B sends 880 Hz.
#
#   sudo bash tests/integration/telephony/sip-calls.sh
#
# Needs: Mira installed and running, deploy/lab-extensions.sh run once, `apt install baresip-core`.
# No pipefail: checks are written "cmd | grep -q ...", and grep -q stops reading at the
# first match, so the writer gets SIGPIPE and pipefail would turn a match into a failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_NAME=sip
# shellcheck source=SCRIPTDIR/lib.sh
. "$HERE/lib.sh"

CREDS="$MIRA_DIR/config/lab-extensions.txt"
[ -s "$CREDS" ] || {
	echo "no lab extensions: sudo ./deploy/lab-extensions.sh"
	exit 2
}
cred() { awk -v e="$1" '$1==e {print $2}' "$CREDS"; }
EXT_A=1001 EXT_B=1002
PASS_A=$(cred $EXT_A) PASS_B=$(cred $EXT_B)

make_phone a 5071 50000 440 "<sip:$EXT_A@$DOMAIN;transport=udp>;auth_pass=$PASS_A;answermode=auto;audio_codecs=PCMU,PCMA;regint=120"
make_phone b 5091 50200 880 "<sip:$EXT_B@$DOMAIN;transport=tls>;auth_pass=$PASS_B;answermode=auto;audio_codecs=PCMU,PCMA;mediaenc=srtp-mand;regint=120"

echo "### 1. phone A (UDP, RTP) calls the echo test 609"
run_phone a 12 "/dial sip:609@$DOMAIN"
sleep 10
stop_phone a
check_tone a 440 "A over UDP hears its own tone back from Asterisk echo"
rm -f "$WORK"/a/rec/*.wav

echo "### 2. phone B (TLS, mandatory SRTP) calls the echo test 609"
run_phone b 12 "/dial sip:609@$DOMAIN"
sleep 10
stop_phone b
# mediaenc=srtp-mand: baresip only connects the call when SRTP was negotiated
if grep -q "Call established" "$WORK/b/log.txt"; then ok "B call connected with mandatory SRTP over TLS"; else bad "B: TLS+SRTP call did not connect"; fi
check_tone b 880 "B over TLS+SRTP hears its own tone back"
rm -f "$WORK"/b/rec/*.wav

echo "### 3. B registers over TLS, A (UDP) calls B"
run_phone b 40
for _ in $(seq 1 15); do
	registered $EXT_B && break
	sleep 1
done
if registered $EXT_B; then ok "B registered over TLS (Asterisk has a contact for $EXT_B)"; else bad "B not registered"; fi
run_phone a 14 "/dial sip:$EXT_B@$DOMAIN"
sleep 12
stop_phone a
# A hung up: Asterisk must reach B over its TLS connection with a BYE (in-dialog routing)
sleep 3
if grep -q "terminated" "$WORK/b/log.txt"; then ok "callee B saw the hang-up (BYE delivered over TLS)"; else bad "callee B never received the BYE"; fi
stop_phone b
check_tone a 880 "caller A hears callee B's tone"
check_tone b 440 "callee B hears caller A's tone"

finish
