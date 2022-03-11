#!/bin/bash
REQUIRED_PYTHON_VERSION=3.8.0
INSTALL_DIR=/opt/sail
BIN_DIR=/usr/local/bin
REQUESTED_VERSION=$1

abort() {
	printf "%s\n" "$@"
	exit 1
}

SUDO=""
if [ ! "$UID" -eq 0 ]; then
	sudo -l mkdir &>/dev/null || abort "This installer requires root or sudo."
	SUDO="sudo "
fi

major_minor() {
	echo "${1%%.*}.$(
		x="${1#*.}"
		echo "${x%%.*}"
	)"
}

version_ge() {
	[[ "${1%.*}" -gt "${2%.*}" ]] || [[ "${1%.*}" -eq "${2%.*}" && "${1#*.}" -ge "${2#*.}" ]]
}

OS="$(uname)"
if [[ "${OS}" != "Linux" ]] && [[ "${OS}" != "Darwin" ]]; then
	abort "Sail CLI is only supported on macOS and Linux. Windows users can use Sail via WSL."
fi

test_python() {
	local python_version_output
	python_version_output="$("$1" --version 2>/dev/null)"
	version_ge "$(major_minor "${python_version_output##* }")" "$(major_minor "${REQUIRED_PYTHON_VERSION}")"
}

git --version || abort "Sail CLI requires Git."
curl --version || abort "Sail CLI requires the cURL binary."
rsync --version || abort "Sail CLI requires rsync."

PYTHON_BIN=""
if test_python python; then
	PYTHON_BIN=$(which python)
elif test_python python3; then
	PYTHON_BIN=$(which python3)
elif test_python python3.8; then
	PYTHON_BIN=$(which python3.8)
fi

if [[ -z ${PYTHON_BIN} ]]; then
	abort "Sail CLI requires Python version ${REQUIRED_PYTHON_VERSION} and above."
fi

$PYTHON_BIN -m venv --help > /dev/null || abort "Sail CLI requires the venv module for Python."
$PYTHON_BIN -m ensurepip --version || abort "Sail CLI requires the python3-venv and python3-pip."

if [ -d $INSTALL_DIR ]; then
	# Make sure it's a Sail CLI installation
	if [ ! -f "$INSTALL_DIR/sail.py" ]; then
		abort "The ${INSTALL_DIR} directory exists and doesn't look like a Sail CLI installation."
	fi

	echo "An existing Sail CLI installation found in ${INSTALL_DIR}. Reinstalling..."
	$SUDO rm -rf $INSTALL_DIR || abort "Could not delete ${INSTALL_DIR}. Are you root?"
fi

$SUDO mkdir $INSTALL_DIR || abort "Could not create directory ${INSTALL_DIR}. Are you root?"
cd $INSTALL_DIR || abort "Could not enter directory ${INSTALL_DIR}. Make sure you have correct permissions."
TARGET_VERSION=$(curl --silent "https://api.github.com/repos/kovshenin/sail/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')

if [ -z $TARGET_VERSION ]; then
	TARGET_VERSION="main"
fi

if [ "$REQUESTED_VERSION" = "mainline" ]; then
	REQUESTED_VERSION="main"
fi

if [ ! -z $REQUESTED_VERSION ]; then
	TARGET_VERSION=$REQUESTED_VERSION
fi

$SUDO git clone https://github.com/kovshenin/sail.git . || abort "Could not clone Git repository."
$SUDO git fetch --all --tags || abort "Could not fetch tags from Git repository."
$SUDO git checkout "${TARGET_VERSION}" || abort "Could not find target version: ${TARGET_VERSION}."

$SUDO $PYTHON_BIN -m venv "${INSTALL_DIR}/.env" || abort "Could not initialize a Python venv."
$SUDO .env/bin/python -m ensurepip --upgrade || abort "Could not ensure pip."
$SUDO .env/bin/pip install pip --upgrade || abort "Could not upgrade pip."
$SUDO .env/bin/pip install -r requirements.txt || abort "Could not install dependencies."
$SUDO .env/bin/python setup.py install || abort "Something went wrong during setup.py install."

$SUDO rm "${BIN_DIR}/sail"
$SUDO ln -s "${INSTALL_DIR}/.env/bin/sail" "${BIN_DIR}/sail" || abort "Could not symlink ${INSTALL_DIR}"

sail_version=$("${BIN_DIR}/sail" --version) || abort "Could not determine Sail CLI version. Install might be corrupted."

echo
echo "# Sail CLI installed successfully"
echo "- Version: ${sail_version}"
echo "- Executable: ${BIN_DIR}/sail"
