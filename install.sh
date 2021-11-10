#!/bin/bash
REQUIRED_GIT_VERSION=2.7.0
REQUIRED_PYTHON_VERSION=3.6.0
INSTALL_DIR=/opt/sail
BIN_DIR=/usr/local/bin
REQUESTED_VERSION=$1

abort() {
	printf "%s\n" "$@"
	exit 1
}

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

test_git() {
	local git_version_output
	git_version_output="$(git --version 2>/dev/null)"
	version_ge "$(major_minor "${git_version_output##* }")" "$(major_minor "${REQUIRED_GIT_VERSION}")"
}

test_python() {
	local python_version_output
	python_version_output="$("$1" --version 2>/dev/null)"
	version_ge "$(major_minor "${python_version_output##* }")" "$(major_minor "${REQUIRED_PYTHON_VERSION}")"
}

test_git || abort "Sail CLI requires Git version ${REQUIRED_GIT_VERSION} and above."
curl --version || abort "Sail CLI requires the cURL binary."

PYTHON_BIN=""
if test_python python; then
	PYTHON_BIN=$(which python)
elif test_python python3; then
	PYTHON_BIN=$(which python3)
fi

if [[ -z ${PYTHON_BIN} ]]; then
	abort "Sail CLI requires Python version ${REQUIRED_PYTHON_VERSION} and above."
fi

if [ -d $INSTALL_DIR ]; then
	abort "The ${INSTALL_DIR} directory already exists. Delete first."
fi

mkdir $INSTALL_DIR || abort "Could not create directory ${INSTALL_DIR}. Are you root?"
cd $INSTALL_DIR || abort "Could not enter directory ${INSTALL_DIR}. Make sure you have correct permissions."
TARGET_VERSION=$(curl --silent "https://api.github.com/repos/kovshenin/sail/releases/latest" | grep -Po '"tag_name": "\K.*?(?=")')

if [ -z $TARGET_VERSION ]; then
	TARGET_VERSION="main"
fi

if [ "$REQUESTED_VERSION" = "mainline" ]; then
	REQUESTED_VERSION="main"
fi

if [ ! -z $REQUESTED_VERSION ]; then
	TARGET_VERSION=$REQUESTED_VERSION
fi

git clone https://github.com/kovshenin/sail.git . || abort "Could not clone Git repository."
git fetch --all --tags || abort "Could not fetch tags from Git repository."
git checkout "${TARGET_VERSION}" || abort "Could not find target version: ${TARGET_VERSION}."

$PYTHON_BIN -m venv "${INSTALL_DIR}/.env"
.env/bin/pip install -r requirements.txt
.env/bin/python setup.py install

rm "${BIN_DIR}/sail"
ln -s "${INSTALL_DIR}/.env/bin/sail" "${BIN_DIR}/sail"
sail_version=$("${BIN_DIR}/sail" --version)

echo
echo "# Sail CLI installed successfully"
echo "- Version: ${sail_version}"
echo "- Executable: ${BIN_DIR}/sail"
