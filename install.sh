#!/usr/bin/env bash
# Cougstival leaderboard installer for Ubuntu Desktop 22.04 / 24.04.
#
#   curl -fsSL https://raw.githubusercontent.com/gizmo564/cougstival/main/install.sh | bash
#
# Safe to run again. Anything you type for passwords or private URLs is hidden, never printed, and goes
# straight into ~/cougstival/.env (readable only by you).
set -euo pipefail

REPO="gizmo564/cougstival"
DIR="$HOME/cougstival"
KEY="$HOME/.ssh/cougstival_deploy"
SITE_URL="https://gizmo564.github.io/cougstival/"

say() { printf '\n==> %s\n' "$*"; }

ask() {          # visible input; the prompt goes to the screen, the answer to stdout
  local v
  IFS= read -r -p "$1" v </dev/tty
  printf '%s' "$v"
}

ask_secret() {   # hidden input
  local v
  IFS= read -rs -p "$1" v </dev/tty
  printf '\n' >&2
  printf '%s' "$v"
}

shq() {          # wrap in single quotes so the shell can read it back exactly, whatever characters it holds
  printf "'%s'" "${1//\'/\'\\\'\'}"
}

write_env() {    # args: email password topic ping_url git_email
  (
    umask 077
    {
      echo "# Written by install.sh. Never commit this file."
      echo "GC_EMAIL=$(shq "$1")"
      echo "GC_PASSWORD=$(shq "$2")"
      echo "NTFY_TOPIC=$(shq "$3")"
      echo "PING_URL=$(shq "$4")"
      echo "GIT_EMAIL=$(shq "$5")"
      echo "PUBLISH='1'"
    } > "$DIR/.env.tmp"
  )
  mv "$DIR/.env.tmp" "$DIR/.env"
  chmod 600 "$DIR/.env"
}

collect_env() {
  if [ -f "$DIR/.env" ]; then
    case "$(ask 'A .env file already exists. Keep it? [Y/n] ')" in
      n|N) ;;
      *) say "Keeping the existing .env"; return ;;
    esac
  fi
  say "Settings. Hidden fields show nothing as you type; you'll only see how many characters arrived."
  local email pw pw2 topic ping gitemail
  email="$(ask 'Goosechase studio login email: ')"
  while :; do
    pw="$(ask_secret 'Goosechase password (hidden): ')"
    pw2="$(ask_secret 'Type it again (hidden): ')"
    if [ -n "$pw" ] && [ "$pw" = "$pw2" ]; then break; fi
    echo "Those did not match, or were empty. Try again."
  done
  topic="$(ask_secret 'ntfy topic for alerts (hidden): ')"
  echo "  ${#topic} characters received"
  ping="$(ask_secret 'healthchecks.io ping URL (hidden; press Enter to skip): ')"
  echo "  ${#ping} characters received"
  gitemail="$(ask 'Email to put on the Team Rocket commits (your GitHub no-reply address keeps your real one private): ')"
  write_env "$email" "$pw" "$topic" "$ping" "$gitemail"
  say ".env written (permissions: only you can read it)"
}

install_packages() {
  say "Installing system packages (you may be asked for your password)"
  sudo apt-get update -y
  sudo apt-get install -y git python3 python3-venv python3-pip curl openssh-client
}

get_code() {
  if [ -d "$DIR/.git" ]; then
    say "Updating $DIR"
    git -C "$DIR" pull --ff-only
  else
    say "Downloading the code into $DIR"
    git clone "https://github.com/$REPO.git" "$DIR"
  fi
  chmod +x "$DIR"/*.sh   # make sure the helper scripts are runnable
}

install_browser() {
  say "Installing Python packages and the headless browser (a few minutes)"
  cd "$DIR"
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install -q --upgrade playwright
  sudo "$DIR/.venv/bin/playwright" install-deps chromium
  .venv/bin/playwright install chromium
}

setup_deploy_key() {
  say "Letting this machine publish the leaderboard to GitHub"
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -f "$KEY" -C "cougstival-box"
  git -C "$DIR" remote set-url origin "git@github.com:$REPO.git"
  git -C "$DIR" config core.sshCommand "ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
  until git -C "$DIR" push --dry-run origin HEAD:main >/dev/null 2>&1; do
    cat <<EOF

GitHub does not accept this machine yet. Add its key (one time):
  1. Open https://github.com/$REPO/settings/keys/new
  2. Title: cougstival box
  3. Paste this key, and TICK "Allow write access":

$(cat "$KEY.pub")

EOF
    case "$(ask 'Press Enter once you have added it (or type s to skip publishing): ')" in
      s|S) echo "Skipping. The site will NOT update until a key is added and this installer is run again."; return ;;
    esac
  done
  echo "GitHub accepts this machine."
}

check_login() {
  say "Testing the Goosechase login (headless)"
  cd "$DIR"
  if ! ./spike.sh; then
    say "Headless login failed. Opening a visible browser. If a login page or captcha appears, complete it by hand; the session is remembered."
    ./spike.sh --headed || { echo "Login still failing. Stop here and send Claude the output above (no passwords)."; exit 1; }
  fi
}

check_alerts() {
  say "Sending a test alert and a test ping"
  cd "$DIR"
  ./run.sh --test-alert
  ./run.sh --test-ping
  echo "Check your phone for the test alert, and healthchecks.io for the ping."
}

first_update() {
  say "Running one real update (also publishes the site)"
  cd "$DIR"
  ./run.sh || { echo "The first update failed. See the message above."; exit 1; }
}

keep_awake() {
  say "Turning off sleep and suspend so the machine keeps running all week"
  sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
  echo "  To undo later: sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target"
  if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)" != "yes" ]; then
    echo "  WARNING: the clock does not report as synchronized. The day windows depend on correct time."
  fi
}

install_service() {
  say "Installing the always-on service"
  sudo tee /etc/systemd/system/cougstival.service >/dev/null <<EOF
[Unit]
Description=Cougstival leaderboard scheduler
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$DIR/loop.sh
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now cougstival
}

main() {
  if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not root. It asks for sudo when needed."
    exit 1
  fi
  command -v apt-get >/dev/null || { echo "This installer is for Ubuntu (apt)."; exit 1; }

  install_packages
  get_code
  install_browser
  collect_env
  setup_deploy_key
  check_login
  check_alerts
  first_update
  keep_awake
  install_service

  cat <<EOF

==> Done. The leaderboard is running.
  Website:      $SITE_URL   (give GitHub a minute or two after the first update)
  Is it alive:  systemctl status cougstival
  Live log:     journalctl -u cougstival -f
  Stop / start: sudo systemctl stop cougstival   /   sudo systemctl start cougstival
  Update code:  cd $DIR && git pull && sudo systemctl restart cougstival
EOF
}

# Everything is defined before anything runs, so a cut-off download can't run half a script.
if [ -z "${COUGSTIVAL_SOURCE_ONLY:-}" ]; then
  main "$@"
fi
