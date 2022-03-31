import os
import re
import shutil
from typing import Union

import requests
from InquirerPy import inquirer
from InquirerPy.base import Choice
from InquirerPy.validator import EmptyInputValidator
from bs4 import BeautifulSoup
from colorama import init
from requests import Response
from termcolor import colored

VERSION = "1.0.0"
NIF_SCRAPE_TEMPLATE: str = "https://nifteam.info/Multimedia/?Anime=%key%"
NIF_DL_TEMPLATE: str = "https://download.nifteam.info/Download/Anime/%episode%"
NIF_HOME_KEY: str = "Homepage"
SERIES_REGEX: str = r"//nifteam.info/Multimedia/\?Anime=.+"
SERIES_EPISODES_REGEX: str = r"//nifteam.info/link.php\?file=.+"


def make_soup(url: str) -> BeautifulSoup:
    page_src: Response = requests.get(url)
    if page_src.status_code != 200:
        print(colored("NIF website is not reachable at the moment!", "red"))
        exit(-1)
    return BeautifulSoup(page_src.text, "html.parser")


def a_to_dict(soup: BeautifulSoup, regex: str) -> dict[str, str]:
    collection: dict[str, str] = {}
    div = soup.find("div", attrs={'class': "nifteam0"})
    for a_element in div.find_all("a", attrs={'href': re.compile(regex)}):
        name: str = a_element.contents[0]
        anime_path: str = a_element['href'].split("=")[1]
        collection[name] = anime_path
    return collection


def get_series(soup: BeautifulSoup) -> [dict[str, str]]:
    in_progress: dict[str, str] = {}
    in_progress_div = soup.find("div", attrs={'id': "listarow"})
    for a_element in in_progress_div.find_all("a", attrs={'href': re.compile(SERIES_REGEX)}):
        name: str = a_element.find("img")['alt']
        anime_path: str = a_element['href'].split("=")[1]
        in_progress[name] = anime_path
    return [in_progress, a_to_dict(soup, SERIES_REGEX)]


def get_series_episodes(soup: BeautifulSoup) -> dict[str, str]:
    return a_to_dict(soup, SERIES_EPISODES_REGEX)


def ask_selection(title: str, choices: [Choice]) -> int:
    return inquirer.select(
        message=title,
        choices=choices,
        default=0).execute()


def ask_fuzzy(title: str, data: [str], episode_listing: bool = False) -> str:
    choices: [Union[str, list['Choice']]] = [
        Choice(value="dumper_goback", name="Go Back to Selection"),
        Choice(value="dumper_exit", name="Exit")
    ]
    if episode_listing:
        choices.append(Choice(value="dumper_download_all", name="Download All (Offset can be set)"))
    choices = choices + data
    return inquirer.fuzzy(
        message=title,
        choices=choices
    ).execute()


def ask_integer_parameter(title: str, min_value: int, max_value: int, default: int = 1) -> int:
    return inquirer.number(
        message=title,
        min_allowed=min_value,
        max_allowed=max_value,
        validate=EmptyInputValidator(),
        default=default
    ).execute()


def download(anime: str, download_action: str, episodes: dict[str, str]) -> None:
    parallel_downloads: int = 1
    current_path: str = "./"
    subdir_needed: bool = True if os.path.isdir(anime) else inquirer.confirm(message=f'Create "{anime}" subfolder?',
                                                                             default=False).execute()
    if subdir_needed:
        try:
            os.makedirs(f'{current_path}{anime}', exist_ok=True)
            current_path = f'{current_path}{anime}'
        except OSError:
            print(colored("Unable to create subfolder!", "red"))
    if download_action != "dumper_download_all":
        url: str = f'\"{NIF_DL_TEMPLATE.replace("%episode%", episodes[download_action])}\"'
    else:
        offset: int = 1
        limit: int = len(episodes.values())
        offset_needed: bool = inquirer.confirm(message="Do you want to set a offset?", default=False).execute()
        if offset_needed:
            offset = ask_integer_parameter("What episode should I start with?:", 1, limit)
        more_parallel: bool = inquirer.confirm(message="Do you want to download more than 1 episode at once?",
                                               default=False).execute()
        if more_parallel:
            parallel_downloads = ask_integer_parameter("How many parallel downloads do you want? (max 5):", 1, 5)
        ep_list: [str] = list(episodes.keys())
        url = ""
        for i in range(int(offset) - 1, limit):
            url: str = f'{url}\"{NIF_DL_TEMPLATE.replace("%episode%", episodes[ep_list[i]])}\" '
    print(colored("\nRunning aria2, to interrupt download press CTRL+C...", "yellow"))
    os.system(f'aria2c -d {current_path} -j {parallel_downloads} --download-result=hide --summary-interval=0 -x 15 -s '
              f'15 -Z {url}')


def runtime(series_list: [dict[str, str]]):
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            series_type = ask_selection("Select anime's category:", [
                Choice(value=0, name="Fansub WIP"),
                Choice(value=1, name="Fansub Completed"),
                Choice(value=-1, name="Exit")
            ])
            if series_type == -1:
                break
            selected_series: str = ask_fuzzy("Select an Anime:", list(series_list[series_type].keys()))
            if selected_series == "dumper_exit":
                break
            elif selected_series == "dumper_goback":
                continue
            else:
                print(colored("Fetching episodes...", "yellow"))
                anime_path: str = series_list[series_type][selected_series]
                episode_soup: BeautifulSoup = make_soup(NIF_SCRAPE_TEMPLATE.replace("%key%", anime_path))
                print(colored("Fetch completed", "green"))
                episodes: dict[str, str] = get_series_episodes(episode_soup)
                download_action: str = ask_fuzzy("Select download item:", list(episodes.keys()), episode_listing=True)
                if download_action == "dumper_exit":
                    break
                elif download_action == "dumper_goback":
                    continue
                download(anime_path, download_action, episodes)
                print(colored("Download completed", "green"))
                exit_confirm = ask_selection("Do you want to dump another anime?:", [
                    Choice(value=0, name="Yes"),
                    Choice(value=1, name="No")
                ])
                if exit_confirm:
                    break
    except KeyboardInterrupt:
        print(colored("\nRuntime aborted by KeyboardInterrupt", "red"))
        exit(-1)


def main() -> None:
    # colorama init
    init()
    if not shutil.which("aria2c"):
        print(colored("aria2 is required to run the dumper!\nInstall it and put it in the PATH!", "red"))
        exit(-1)
    print(colored("Fetching NIF releases...", "yellow"))
    soup: BeautifulSoup = make_soup(NIF_SCRAPE_TEMPLATE.replace("%key%", NIF_HOME_KEY))
    print(colored("Fetch completed!", "green"))
    runtime(get_series(soup))
    print(colored("Thanks you, goodbye!", "cyan"))


if __name__ == '__main__':
    main()
