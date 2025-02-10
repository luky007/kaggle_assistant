#!/bin/bash

# This file contains the code that will run after the SSH connections is established.
# It will install all the common software.

### install miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash ./Miniconda3-latest-Linux-x86_64.sh -b -u -p $HOME/miniconda3
source $HOME/miniconda3/bin/activate
$HOME/miniconda3/bin/conda init
$HOME/miniconda3/bin/conda update -n base conda -y
rm Miniconda3-latest-Linux-x86_64.sh

### install cuda
if lspci | grep -i NVIDIA; then
echo "NVIDIA device found"
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
rm cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-toolkit-12-4
else
echo "NVIDIA device not found"
fi

### install ollama # https://superuser.com/questions/454907/how-to-execute-a-command-in-screen-and-detach
curl https://ollama.ai/install.sh | sh

## install ai-model
#screen -S ollama_serve -dm bash -c 'ollama serve'
#screen -S ollama_serve -dm bash -c 'sleep 10; ollama run mixtral:8x7b-instruct-v0.1-q5_K_M; exec sh'

## install custom version
#sudo curl -L https://github.com/ollama/ollama/releases/download/v0.1.28/ollama-linux-amd64 -o /usr/bin/ollama
#sudo chmod +x /usr/bin/ollama

### install syncthing
sudo curl -o /usr/share/keyrings/syncthing-archive-keyring.gpg https://syncthing.net/release-key.gpg
echo "deb [signed-by=/usr/share/keyrings/syncthing-archive-keyring.gpg] https://apt.syncthing.net/ syncthing stable" | sudo tee /etc/apt/sources.list.d/syncthing.list
sudo apt-get update -y
sudo apt-get install syncthing -y
syncthing >/dev/null 2>&1 &

### personal stuff
sudo apt-get install htop nvtop tldr nano micro net-tools fish zsh pipx psmisc exa -y
pipx ensurepath
pipx install oterm
tldr --update
$HOME/miniconda3/bin/conda run -n base pip install conda-lock

wget https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz
tar -xvf zellij*.tar.gz && rm zellij*.tar.gz && mv zellij /usr/bin/zellij

sudo apt-get install npm -y && sudo npm install --global carbonyl # for debugging syncthing web UI

### install playwright
$HOME/miniconda3/bin/conda create -n kaggle_pinger python=3.11 -y
$HOME/miniconda3/bin/conda run -n kaggle_pinger pip install playwright
$HOME/miniconda3/bin/conda run -n kaggle_pinger playwright install-deps
$HOME/miniconda3/bin/conda run -n kaggle_pinger playwright install