> Note
> Only Windows OS is currently fully supported.

# Kaggle assistant

Connect with ssh to kaggle with more ease.

Features:

- Allow the user to pick the wanted hardware

- Automatically open the created ssh tunnel inside VScode (Windows only)

- Automatically share a Syncthing folder (Windows only)

## How to run it: 🏃

### Using docker container

- Copy `.env.example` to `.env` and fill it with your settings.

- Generate a pub and private ssh key with:

  ```bash
  ssh-keygen -t rsa
  ```

  Then copy `id_rsa` `id_rsa.pub` also to the top level of this project directory.

- :whale: Open this project inside a docker container with GUI.
Use WSL2 or [this command](https://www.youtube.com/embed/dihfA7Ol6Mw?t=102) `xhost +local:` under linux.
Select python ENV conda (base) in Vscode and run `main.py`. 

### Manual install

- :snake: Setup the conda environment with:
  
  ```bash
  conda-lock install -n kaggle_ssh .\conda-lock.yml
  ```

- :package: Then initialize the project dependencies by using Poetry:
  
  ```bash
  poetry install
  ```

- Under Windows OS install the following program:
  
  - [Synctrayzor](https://github.com/canton7/SyncTrayzor)
  
  - [VScodium](https://github.com/VSCodium/vscodium)

- Copy `.env.example` to `.env` and fill it with your settings.

  ```sh
  MAIL_USERNAME_KAGGLE=# your Kaggle username
  PASSWORD_KAGGLE=# your Kaggle password
  URL_NOTEBOOK_KAGGLE=# Es: https://www.kaggle.com/code/your_kaggle_user/your_kaggle_notebook/edit
  NGROK_TOKEN=# get it from www.ngrok.com

  ### The following will be used for Windows OS only. These are required.
  PATH_VSCODE=# es: C:\Program Files\VSCodium\bin\codium.cmd
  ID_SYNCTHING=# your Syncthing ID. Like es: 0000000-0000000-0000000-0000000-0000000-0000000-0000000-0000000
  ID_FOLDER_TO_SHARE_SYNCTHING=# the ID of the Synthing folder that you want to appear on Kaggle. Like es: test-test
  PATH_SYNCTRAYZOR=# Es: C:\Program Files\SyncTrayzor\SyncTrayzor.exe
  PATH_SYNCTHING=# Es: C:\Program Files\SyncTrayzor\syncthing.exe
  ```

- If needed generate a public ssh key by using:
  
  ```bash
  ssh-keygen -t rsa
  ```
  Then copy `id_rsa` `id_rsa.pub` also to the top level of this project directory.

### TODO 🎯

[ ] Improve code quality.

[ ] Set an auto pinger for avoiding poweroff due to user inactivity. 

[ ] Make optional installing Vscode and Syncthing on Windows.

[ ] Ask user for folder id to share by using a TUI menu.

[ ] Use Paramiko for sending folder. Ngrok do not limit upload only download. Synthing is really slow for that task.

[ ] Allow user to pick which list of .sh commands to run at the start.

[ ] Add full support for Linux.