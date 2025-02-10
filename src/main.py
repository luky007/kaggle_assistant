"""Use kaggle notebook throughout SSH. Automatically set up VScode and share a syncthing folder."""

import base64
import json
import logging
import os
import platform
import re
import secrets
import string
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

import requests
import rich.traceback
import spur  # pyright: ignore[reportMissingTypeStubs]
from dotenv import load_dotenv
from playwright.sync_api import Locator, Page, Playwright, sync_playwright
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.prompt import IntPrompt
from rich.theme import Theme


def remove_comments(code: str, symbol: str) -> str:
    """Utility function for remove everything character is line after specified symbol.

    Args:
        code (str): the input text to clean
        symbol (str): the symbol to remove

    Returns:
        str: the cleaned text
    """
    lines = code.split("\n")
    modified_lines = [line.split(symbol, 1)[0] for line in lines]
    return "\n".join(modified_lines)


def extract_code_and_markdown_from_ipynb(path_ipynb: Path) -> tuple[str, str]:
    """Read an ipynb file and extract the code and the markdown text.

    Do not read metadata so it will return every scripting language.

    Args:
        path_ipynb (Path): The path of the file to import.

    Returns:
        tuple[str, str]: The code and the markdown text
    """
    code, markdown = "", ""
    with open(path_ipynb, encoding="UTF-8") as file:
        data = json.load(file)

    for cell in data["cells"]:
        if cell["cell_type"] == "markdown":
            for source in cell["source"]:
                markdown += source.rstrip() + "\n"
        if cell["cell_type"] == "code":
            for source in cell["source"]:
                code += source.rstrip() + "\n"

    return code, markdown


def open_kaggle(
    playwright: Playwright,
    mail_or_username: str,
    password: str,
    url_notebook: str,
    headless: bool,
) -> Page:
    """Login into kaggle and open a notebook.

    Args:
        playwright (Playwright): the Playwright instance to use.
        headless (bool): run the browser in background yes or no.
        mail_or_username (str): the mail or username for the login.
        password (str): the password to use for the login.
        url_notebook (str): the url of the kaggle notebook to open after the login.

    Returns:
        Page: Return the Page instance required for further interacting with kaggle.
    """
    logger = logging.getLogger(Path(__file__).stem)
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context()
    page = context.new_page()
    logger.info("Browser opened")
    page.goto(
        r"https://www.kaggle.com/account/login?phase=emailSignIn&returnUrl=%2F",
        timeout=120000,
    )
    page.get_by_placeholder("Enter your email address or username").fill(
        mail_or_username
    )
    page.get_by_placeholder("Enter password").fill(password)
    page.get_by_text("OK, Got it.").click()
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url("https://www.kaggle.com/")
    logger.info("Login completed")
    page.goto(url_notebook)
    page.frame_locator('iframe[name="notebook-editor-cells"]').get_by_role(
        "button", name="Execute cell"
    ).wait_for(state="visible")  # the cell's run button is the last thing to load
    logger.info("Now on notebook url: %s", url_notebook)
    return page


def get_running_status(page: Page) -> Literal["OFF", "LOADING", "RUNNING"]:
    """Determines the running status of a page based on the visibility and color of a span element.

    This function checks for the presence of a span element with specific ARIA labels that indicate
    the running status of a process on the page. It evaluates the color of the found element to
    return one of three possible statuses: "OFF", "LOADING", or "RUNNING".

    Args:
        page (Page): The page object representing the current state of the web page.

    Returns:
        Literal["OFF", "LOADING", "RUNNING"]: The running status of the page, which can be one of
        the following:
            - "OFF": Indicates that the process is not running.
            - "LOADING": Indicates that the process is currently loading.
            - "RUNNING": Indicates that the process is currently running.

    Raises:
        AssertionError: If the span element is found but has an unknown color.
        AssertionError: If the span element is not found on the page.
    """
    aria_labels = {"off (run a cell to start)", "Running", "Starting", "Loading"}
    span_element = None

    # Loop through the aria labels to find a visible span element
    for label in aria_labels:
        span_element = page.query_selector(f'span[aria-label="{label}"]')
        if span_element and span_element.is_visible():
            break  # Exit the loop if a visible element is found

    if span_element:
        color = span_element.evaluate(
            "element => window.getComputedStyle(element).color"
        )
        if color == "rgb(95, 99, 104)":
            return "OFF"
        if color == "rgb(214, 173, 27)":
            return "LOADING"
        if color == "rgb(25, 118, 49)":
            return "RUNNING"
        raise AssertionError(
            "The circle indicator has found in the page, but has an unknown color."
        )

    raise AssertionError("The circle indicator has not been found in the page.")


def is_kaggle_running(page: Page, timeout: int = 120) -> bool:
    """Check if kaggle is running or not.

    Args:
        page (Page): the Page instance to use. Needs to be on a notebook page.
        timeout (int, optional): the maximum time to wait. Defaults to 120.

    Raises:
        TimeoutError: The maximum time is reached.
        AssertionError: Both the on and off indicator are visible.

    Returns:
        bool: return True if running else False.
    """
    for _ in range(timeout):
        if get_running_status(page) == "RUNNING":
            return True
        if get_running_status(page) == "OFF":
            return False
        time.sleep(1)
    raise TimeoutError(f"The page appears to be still loading after {timeout} seconds")


def turn_on(
    page: Page,
    hardware_wanted: Literal["None", "GPU T4 x2", "GPU P100", "TPU VM v3-8"],
) -> None:
    """Turn on a kaggle notebook with the selected hardware.

    Args:
        page (Page): the Page instance to use. Needs to be on a notebook page.
        hardware_wanted (Literal["None", "GPU T4 x2", "GPU P100", "TPU VM v3-8"]): hardware to use.

    Raises:
        AssertionError: unable to get the current hardware specs.
    """
    logger = logging.getLogger(Path(__file__).stem)
    kaggle_hardware_options = page.get_by_text("Session optionskeyboard_arrow_down")
    if kaggle_hardware_options.is_visible():
        kaggle_hardware_options.click()
    none_pc, gpu_x2_pc, gpu_x1_pc, tpu_pc = (
        page.get_by_text("None"),
        page.get_by_text("GPU T4 x2"),
        page.get_by_text("GPU P100"),
        page.get_by_text("TPU VM v3-8"),
    )
    current_pc: list[Locator] = []
    if none_pc.is_visible():
        logger.info("CPU only currently selected as a accelerator")
        current_pc.append(none_pc)
    if gpu_x2_pc.is_visible():
        logger.info("Double GPU currently selected as a accelerator")
        current_pc.append(gpu_x2_pc)
    if gpu_x1_pc.is_visible():
        logger.info("Single GPU currently selected as a accelerator")
        current_pc.append(gpu_x1_pc)
    if tpu_pc.is_visible():
        logger.info("Tpu currently selected as a accelerator")
        current_pc.append(tpu_pc)

    if len(current_pc) == 1:
        hardware_selected = current_pc[0].inner_text().split("\n")[0]
        page.get_by_text(hardware_selected, exact=True).click()
        page.get_by_label(hardware_wanted, exact=True).click()

        if hardware_wanted not in ("None"):
            time_quota = page.get_by_text(re.compile("[1-9][0-9] hrs"))
            logger.info(f"Quota remaining: {time_quota.all_text_contents()}")
        if hardware_wanted not in (hardware_selected, "None"):
            page.get_by_role("button", name=f"Turn on {hardware_wanted}").click()
        page.get_by_label("Run current cell").click()
    else:
        raise AssertionError("The hardware is not uniquely defined.")
    logger.info(
        "Executed dummy cell on kaggle with hardware: %s before was %s",
        hardware_wanted,
        hardware_selected,
    )


def run_in_kaggle_terminal(page: Page, code_to_run: str, clear_log: bool) -> None:
    """Run a code inside the Kaggle terminal.

    Args:
        page (Page): the Page instance to use. Needs to be on a notebook page.
        code_to_run (str): the code to execute in the terminal. Requires the use of ! for bash.
        clear_log (bool): clear or not the log soon after insertions.
    """
    logger = logging.getLogger(Path(__file__).stem)
    terminal_prompt = page.get_by_placeholder("Enter console command here")
    if terminal_prompt.is_visible() is False:
        page.get_by_label("Open console").click()
    terminal_prompt.fill(code_to_run)
    terminal_prompt.press("Enter")
    logger.info("Code executed inside kaggle console")
    if clear_log:
        page.get_by_role("button", name="Clear").click()
        logger.info("Cleared the console log")


def get_url_ngrok(page: Page, timeout: int = 120) -> tuple[str, int]:
    """Get the ngrok url written in kaggle console log. Clear the log soon after.

    Args:
        page (Page): the Page instance to use. Needs to be on a notebook page.
        timeout (int, optional): the maximum time to wait. Defaults to 120.

    Raises:
        AssertionError: The page has no text.
        TimeoutError: The maximum time is reached.
        ValueError: The port is not an integer.

    Returns:
        tuple[str, int]: return url and the port number.
    """
    logger = logging.getLogger(Path(__file__).stem)
    logger.info("Started searching for the ngrok url on page")
    second_loading = 0
    while timeout > second_loading:
        text_on_page = page.text_content("body")
        if text_on_page is None:
            raise AssertionError("There is not text in page.")
        ngrok_ip = {word for word in text_on_page.split() if ".tcp.eu.ngrok." in word}
        if ngrok_ip:
            break
    else:
        raise TimeoutError(f"ngrok ip not found after {timeout} seconds")

    ssh_domain, ssh_port = ngrok_ip.pop().split(":")
    match = re.search(r"\d+", ssh_port)
    if match is not None:
        n_ssh_port = int(match.group())
        logger.info("Found url ngrok: %s:%s", ssh_domain, n_ssh_port)
        return ssh_domain, n_ssh_port
    raise ValueError(f"The port is not an integer: {ssh_port}")


def send_command_to_ssh(
    ssh_domain: str, ssh_port: int, password: str, code_to_run: str, user: str = "root"
) -> None:
    """Execute on the target machine a series of sh commands inside a ssh tunnel.

    Encode the code in base64 before send it, then decode and run it on the target machine.

    Args:
        ssh_domain (str): the domain of the machine.
        ssh_port (int): the port for the ssh.
        password (str): the ssh password.
        code_to_run (str): the series of sh commands to run.
        user (str, optional): the username to login into. Defaults to "root".
    """
    logger = logging.getLogger(Path(__file__).stem)
    remote_shell: spur.SshShell = spur.SshShell(
        hostname=ssh_domain,
        port=ssh_port,
        username=user,
        password=password,
        missing_host_key=spur.ssh.MissingHostKey.accept,
        shell_type=spur.ssh.ShellTypes.sh,
    )
    base64_text = base64.b64encode(code_to_run.encode()).decode()
    logger.info(
        "Start executing command on remote session. This will require about 10 minutes."
    )
    remote_shell.run(  # type: ignore
        [
            "sh",
            "-c",
            f"echo '{base64_text}' | base64 -d | sh",
        ],
    )
    logger.info("Code executed successfully")


def pull_ollama_model(
    ssh_domain: str,
    ssh_port: int,
    password: str,
    name_model_to_pull: str,
    user: str = "root",
) -> None:
    """Execute on the target machine a series of sh commands inside a ssh tunnel.

    Encode the code in base64 before send it, then decode and run it on the target machine.

    Args:
        ssh_domain (str): the domain of the machine.
        ssh_port (int): the port for the ssh.
        password (str): the ssh password.
        name_model_to_pull (str): the name of the ollama model to pull from the registry.
        user (str, optional): the username to login into. Defaults to "root".
    """
    logger = logging.getLogger(Path(__file__).stem)
    remote_shell: spur.SshShell = spur.SshShell(
        hostname=ssh_domain,
        port=ssh_port,
        username=user,
        password=password,
        missing_host_key=spur.ssh.MissingHostKey.accept,
        shell_type=spur.ssh.ShellTypes.sh,
    )
    pull_command = (
        """curl http://localhost:11434/api/pull -d '{
        "name": "%s"
        }'""",
        name_model_to_pull,
    )
    remote_shell.run(  # type: ignore
        ["sh", "-c", pull_command],
    )
    logger.info("Code executed successfully")


def set_syncthing_sharing_ssh(
    ssh_domain: str, ssh_port: int, password: str, id_syncthing: str, user: str = "root"
) -> str:
    """Allow a id syncthing on a remote machine using ssh. Return the machine syncthing id.

    Args:
        ssh_domain (str): the domain of the machine.
        ssh_port (int): the port for the ssh.
        password (str): the ssh password.
        id_syncthing (str): the id syncthing to allow on the remote machine.
        user (str, optional): the username to login into. Defaults to "root".

    Returns:
        str: the syncthing id of the remote machine.
    """
    logger = logging.getLogger(Path(__file__).stem)
    remote_shell: spur.SshShell = spur.SshShell(
        hostname=ssh_domain,
        port=ssh_port,
        username=user,
        password=password,
        missing_host_key=spur.ssh.MissingHostKey.accept,
        shell_type=spur.ssh.ShellTypes.sh,
    )
    remote_shell.run(  # type: ignore
        [
            "sh",
            "-c",
            f"syncthing cli config devices add --device-id {id_syncthing} --name main --auto-accept-folders --compression always",
        ],
    )
    logger.info("Syncthing sharing allowed on remote machine")
    id_syncthing_kaggle = str(
        remote_shell.run(["sh", "-c", "syncthing --device-id"]).output.decode().strip()  # type: ignore
    )
    logger.info(f"Kaggle syncthing id is: {id_syncthing_kaggle}")
    return id_syncthing_kaggle


def set_ssh_pub_key(
    ssh_domain: str,
    ssh_port: int,
    password: str,
    path_pub_ssh_key: Path,
    user: str = "root",
) -> None:
    """Load a public ssh key into a target machine using ssh.

    Args:
        ssh_domain (str): the domain of the machine.
        ssh_port (int): the port for the ssh.
        password (str): the ssh password.
        path_pub_ssh_key (Path): the path of the public key to import.
        user (str, optional): the username to login into. Defaults to "root".
    """
    logger = logging.getLogger(Path(__file__).stem)
    remote_shell: spur.SshShell = spur.SshShell(
        hostname=ssh_domain,
        port=ssh_port,
        username=user,
        password=password,
        missing_host_key=spur.ssh.MissingHostKey.accept,
        shell_type=spur.ssh.ShellTypes.sh,
    )
    with open(path_pub_ssh_key, encoding="UTF-8") as file:
        ssh_pub_key = file.read()
    command_to_run = " && ".join(
        [
            "mkdir -p $HOME/.ssh/",
            f"echo '{ssh_pub_key}' > $HOME/.ssh/authorized_keys",
            "chmod 700 $HOME/.ssh/",
            "chmod 600 $HOME/.ssh/authorized_keys",
            "service ssh restart",
        ]
    )
    remote_shell.run(  # type: ignore
        [
            "sh",
            "-c",
            command_to_run,
        ]
    )
    logger.info("Successfully sent ssh public key")


def open_vscode(
    path_vscode: Path,
    ssh_domain: str,
    ssh_port: str,
    password_ssh: str,
    user: str = "root",
    folder: str = "/root",
) -> None:
    """Open a ssh connection using VScode. Requires a public key for password-less login.

    Args:
        path_vscode (Path): the path of the VScode.
        ssh_domain (str): the domain of the machine.
        ssh_port (int): the port for the ssh.
        user (str, optional): the username to login into. Defaults to "root".
        folder (str, optional): the folder to open. Defaults to "/root".
    """
    logger = logging.getLogger(Path(__file__).stem)
    logger.info(f"Ready to connected with SSH: {user}@{ssh_domain}:{ssh_port}")
    if platform.system() == "Windows":
        open_vscode_command = f'"{path_vscode}" --remote --folder-uri "vscode-remote://ssh-remote+{user}@{ssh_domain}:{ssh_port}{folder}"'
        subprocess.run(
            open_vscode_command,
            shell=True,
            check=True,
        )
    else:
        logger.warning("Unable to open VScode because not on Windows OS")
        logger.info(
            f'Consider using: codium --remote --folder-uri "vscode-remote://ssh-remote+{user}@{ssh_domain}:{ssh_port}{folder}"'
        )
        logger.info(f"The ssh password if needed is: {password_ssh}")


def turn_off(page: Page) -> None:
    """Turn off a kaggle notebook.

    Args:
        page (Page): the Page instance to use. Needs to be on a notebook page.
    """
    logger = logging.getLogger(Path(__file__).stem)
    if is_kaggle_running(page) is False:
        logger.info("Kaggle notebook was already off")
        return
    page.get_by_label("More settings").click()
    page.get_by_role("menu").get_by_text("power_settings_newStop session").click()
    if is_kaggle_running(page) is False:
        logger.info("Turned off kaggle notebook")
    else:
        logger.warning("Unable to turn off")


def get_env_var(name: str) -> str:
    """A custom version of os.getenv() that raises KeyError if the variable is not defined.

    Args:
        name (str): the name of the env variable to retrieve.

    Raises:
        KeyError: raise error if variable do not exist.

    Returns:
        str: return a text stored inside the variable.
    """
    value = os.getenv(name)
    if value is None:
        msg = f"Environment variable '{name}' not found."
        raise KeyError(msg)
    return value


def get_user_input() -> Literal["GPU P100", "GPU T4 x2", "TPU VM v3-8", "None"] | None:
    """Get the user input from the interactive menu.

    Raises:
        ValueError: User input is out of range.

    Returns:
        str: the user hardware wanted by the user.
    """
    console = Console(theme=Theme({"success": "green", "error": "bold red"}))
    text_menu = (
        "# Kaggle ssh\n"
        "- 1 Start CPU only\n"
        "- 2 Start single GPU\n"
        "- 3 Start double GPU\n"
        "- 4 Start TPU (untested)\n"
        "- 5 Close kaggle\n"
        "\n<br>\n"
    )
    console.print(Markdown(text_menu))
    user_input = IntPrompt.ask(
        "User choice", choices=[str(i) for i in range(1, 6)], default=5
    )
    hardware_wanted = None
    if user_input in {1}:
        hardware_wanted = "None"
    elif user_input in {2}:
        hardware_wanted = "GPU P100"
    elif user_input in {3}:
        hardware_wanted = "GPU T4 x2"
    elif user_input in {4}:
        hardware_wanted = "TPU VM v3-8"
    elif user_input in {5}:
        hardware_wanted = None
    else:
        raise ValueError(f"Wrong user input: {user_input}")
    return hardware_wanted


def delete_device_from_syncthing(
    path_syncthing_conf: Path,
    name_device_to_delete: str,
    path_syncthing: Path,
    path_synctrayzor: Path,
) -> None:
    """Utility function for deleting device with a specific name to syncthing.

    The program will shutdown synctrayzor after clean it. Will be re opened soon after.

    Args:s
        path_syncthing_conf (Path): the path of the config.xml that syncthing uses.
        name_device_to_delete (str): the name of the device to remove.
        path_syncthing (Path): Path of syncthing binary.
        path_synctrayzor (Path): Path of synctrayzor binary.
    """
    logger = logging.getLogger(Path(__file__).stem)
    # subprocess.run(
    #    f'"{path_syncthing}" cli operations shutdown', shell=True, check=True
    # )
    subprocess.run(f'"{path_synctrayzor}" --shutdown', shell=True, check=True)

    root = ET.parse(path_syncthing_conf)
    devices = root.findall("device")
    for dev in devices:
        if "name" in dev.attrib and dev.attrib["name"] == name_device_to_delete:
            dev.clear()  # Clear all child nodes (equivalent to removing them)
    root.write(path_syncthing_conf)

    logger.info(f"Cleaned syncthing configuration file: {path_syncthing_conf}")


def share_syncthing_folder(
    path_syncthing: Path,
    path_synctrayzor: Path,
    id_syncthing_kaggle: str,
    id_folder_to_share_syncthing: str,
    name_folder: str,
) -> None:
    """Share a specific folder over syncthing.

    Args:
        path_syncthing (Path): the syncthing path.
        path_synctrayzor (Path): Path of synctrayzor binary.
        id_syncthing_kaggle (str): the id from the syncthing instance running of kaggle.
        id_folder_to_share_syncthing (str): the id of the folder to share.
        name_folder (str): the name of the folder shared.

    Raises:
        TimeoutError: Tf syncthing server do not go up withing the time limit.
    """
    logger = logging.getLogger(Path(__file__).stem)
    subprocess.Popen(f'"{path_synctrayzor}" --minimized')
    syncthing_server = r"http://127.0.0.1:8384"
    timeout = 20.0
    second_loading = 0
    while timeout > second_loading:
        try:
            requests.get(syncthing_server)
        except requests.ConnectionError:
            pass
        else:
            break
        finally:
            second_loading += 0.1
    else:
        raise TimeoutError(f"Synctrayzor server do not start at {syncthing_server}")

    subprocess.run(
        f'"{path_syncthing}" cli config devices add --device-id {id_syncthing_kaggle} --name {name_folder} --compression always',
        shell=True,
        check=True,
    )
    subprocess.run(
        f'"{path_syncthing}" cli config folders {id_folder_to_share_syncthing} devices add --device-id {id_syncthing_kaggle}',
        shell=True,
        check=True,
    )
    ## Reboot soon after (test if really needed)
    # subprocess.run(f'"{syncthing_path}" cli operations shutdown', shell=True) # also kill this if need to reboot rapidly. Do not use check.
    # subprocess.run(f'"{path_synctrayzor}" --shutdown', shell=True, check=True)
    # subprocess.Popen(f'"{path_synctrayzor}" --minimized')

    logger.info(f"Shared syncthing folder with id: {id_folder_to_share_syncthing}")


def initialize_variables() -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """Initialize and return variables required by the application.

    This function loads environment variables using the `pydotenv` library,
    initializes some additional variables based on these environment variables,
    and checks if certain files/directories exist. If any of the required
    files/directories do not exist, it raises a FileExistsError with an appropriate message.

    Raises:
        FileExistsError: If VScode binary is not found in the specified path.
        FileExistsError: If public ssh key is not found in the default location.
        FileExistsError: If SyncTrayzor is not installed in the expected directory.
        FileExistsError: If Syncthing configuration file is not found in the expected location.

    Returns:
        tuple[tuple[str, ...], tuple[Path, ...]]: A tuple containing two tuples.
        The first tuple consists of initialized variables as strings, and the second tuple contains Path objects for various files/directories.
    """
    load_dotenv()
    url_notebook_kaggle = get_env_var("URL_NOTEBOOK_KAGGLE")
    main_username_kaggle = get_env_var("MAIL_USERNAME_KAGGLE")
    password_kaggle = get_env_var("PASSWORD_KAGGLE")
    ngrok_token = get_env_var("NGROK_TOKEN")
    path_vscode = Path(get_env_var("PATH_VSCODE"))
    id_syncthing = get_env_var("ID_SYNCTHING")
    id_folder_to_share_syncthing = get_env_var("ID_FOLDER_TO_SHARE_SYNCTHING")
    path_synctrayzor = Path(get_env_var("PATH_SYNCTRAYZOR"))
    path_syncthing = Path(get_env_var("PATH_SYNCTHING"))

    path_current_dir = Path(__file__).resolve().parent
    password_ssh = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(64)
    )
    py_code, _ = extract_code_and_markdown_from_ipynb(
        path_current_dir / "kaggle_src" / "open_ngrok_ssh_kaggle.ipynb"
    )
    py_code = py_code.replace("__kaggle_password_placeholder__", password_ssh)
    py_code = py_code.replace("__ngrok_token_placeholder__", ngrok_token)
    bash_code = Path(path_current_dir / "kaggle_src" / "install_command.sh").read_text()
    path_syncthing_conf = (
        Path("~").expanduser() / "AppData" / "Local" / "Syncthing" / "config.xml"
    )
    name_folder_syncthing = "kaggle_TMP"

    # path_pub_ssh_key = Path.home() / ".ssh" / "id_rsa.pub"
    path_pub_ssh_key = Path(path_current_dir.parent / "id_rsa.pub")
    if path_pub_ssh_key.exists() is False:
        raise FileExistsError(
            f"Public ssh key not found in: {path_pub_ssh_key}. Generate one using 'ssh-keygen -t rsa' and copy the public to {Path.home() / '.ssh' / 'id_rsa.pub'}"
        )
    if platform.system() == "Windows":
        if path_vscode.exists() is False:
            raise FileExistsError(f"VScode binary not found in: {path_vscode}")
        if path_synctrayzor.exists() is False or path_syncthing.exists() is False:
            raise FileExistsError(
                f"SyncTrayzor not installed in {path_synctrayzor.parent}"
            )
        if path_syncthing_conf.exists() is False:
            raise FileExistsError(
                f"Syncthing configuration file not found in {path_syncthing_conf}"
            )
    return (
        (
            url_notebook_kaggle,
            main_username_kaggle,
            password_kaggle,
            id_syncthing,
            id_folder_to_share_syncthing,
            password_ssh,
            py_code,
            bash_code,
            name_folder_syncthing,
        ),
        (
            path_vscode,
            path_pub_ssh_key,
            path_synctrayzor,
            path_syncthing,
            path_syncthing_conf,
        ),
    )


def main() -> None:
    """The main function."""
    rich.traceback.install()
    logging.basicConfig(
        level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
    )
    list_str_var, list_path_var = initialize_variables()
    (
        url_notebook_kaggle,
        main_username_kaggle,
        password_kaggle,
        id_syncthing,
        id_folder_to_share_syncthing,
        password_ssh,
        py_code,
        bash_code,
        name_folder_syncthing,
    ) = list_str_var
    (
        path_vscode,
        path_pub_ssh_key,
        path_synctrayzor,
        path_syncthing,
        path_syncthing_conf,
    ) = list_path_var
    use_headless_mode = True

    hardware_wanted = get_user_input()
    if hardware_wanted is None:
        with sync_playwright() as playwright:
            turn_off(
                open_kaggle(
                    playwright,
                    main_username_kaggle,
                    password_kaggle,
                    url_notebook_kaggle,
                    use_headless_mode,
                )
            )
        sys.exit()

    with sync_playwright() as playwright:
        page = open_kaggle(
            playwright,
            main_username_kaggle,
            password_kaggle,
            url_notebook_kaggle,
            use_headless_mode,
        )
        if is_kaggle_running(page=page):
            raise RuntimeError("Kaggle is already running. Close it first")
        turn_on(page=page, hardware_wanted=hardware_wanted)

        if is_kaggle_running(page=page) is False:
            raise RuntimeError("Kaggle did not turn on despite the attempt")
        time.sleep(10)
        run_in_kaggle_terminal(page=page, code_to_run=py_code, clear_log=False)
        ssh_domain, ssh_port = get_url_ngrok(page=page)
        run_in_kaggle_terminal(page=page, code_to_run="", clear_log=True)
        send_command_to_ssh(ssh_domain, ssh_port, password_ssh, bash_code)
        set_ssh_pub_key(ssh_domain, ssh_port, password_ssh, path_pub_ssh_key)
        open_vscode(path_vscode, ssh_domain, str(ssh_port), password_ssh)
        if platform.system() in "Windows":
            delete_device_from_syncthing(
                path_syncthing_conf,
                name_folder_syncthing,
                path_syncthing,
                path_synctrayzor,
            )
            id_syncthing_kaggle = set_syncthing_sharing_ssh(
                ssh_domain, ssh_port, password_ssh, id_syncthing
            )
            share_syncthing_folder(
                path_syncthing,
                path_synctrayzor,
                id_syncthing_kaggle,
                id_folder_to_share_syncthing,
                name_folder_syncthing,
            )


if __name__ == "__main__":
    main()
