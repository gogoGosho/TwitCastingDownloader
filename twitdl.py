import argparse
import base64
import json
import os
import re
import signal
import subprocess
import sys
import traceback
import requests,send2trash
from bs4 import BeautifulSoup
from pathlib import Path
import time
import logging


# TODO Allow user to specify root directory folder name rather than using channel name
# TODO Allow for the single download of passcode protected video i.e. python twitdl.py -l <TwitCasting Link> -p 12345
# TODO Allow user to specify -re and provide their own user-agent
# TODO Allow user to specify directory name for batch download by utilizing % string formatting e.g. print("%(name)s said hi" % {"name": "Sam", "age": "21"})

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
# Adds a link, name, and output argument
# Returns the arguments
def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--link',
                        type=str,
                        metavar='',
                        help="The TwitCasting channel link to scrape and get the video links")

    parser.add_argument('-n', '--name',
                        type=str,
                        nargs='+',
                        metavar='',
                        help="Name of the text archive file. If not specified a default name will be used. "
                             "This argument is used to created the archive text file and this file can be used later in "
                             "the --archive argument. This argument is no longer necessary with the introduction of --archive")

    parser.add_argument('-o', '--output',
                        type=str,
                        nargs='+',
                        help="The user's chosen absolute save path for the download video and/or archive file")

    parser.add_argument('-s', '--scrape',
                        action='store_true',
                        help="Only scrape inputted url and saved as the result in a text file(don't download)")

    parser.add_argument('-f', '--file',
                        type=str,
                        nargs='+',
                        help="Location of the text file that contains a list of the secret words. Can not be called "
                             "along side --passcode")

    parser.add_argument('-p', '--passcode',
                        type=str,
                        nargs='+',
                        help="The secret word to access the locked video. Can not be called along side --file")

    parser.add_argument('-a', '--archive',
                        type=str,
                        nargs='?',
                        help="Location of the archive text file that contains a list of urls pertaining to downloaded videos")

    parser.add_argument('-c', '--cookies',
                        type=str,
                        nargs='+',
                        help="Cookie file path in netscape format")

    args = parser.parse_args()
    return args


def webDriverSetup():
    try:
        from selenium import webdriver
        from selenium.webdriver.common.keys import Keys
        from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.support.wait import WebDriverWait

        # Find a webdriver in path and taking in order of either the chrome driver,
        # firefox driver, edge driver, or opera driver
        while not False:
            try:
                from selenium.webdriver.chrome.service import Service
                from webdriver_manager.chrome import ChromeDriverManager
                chrome_options = webdriver.ChromeOptions()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--mute-audio')
                chrome_options.add_argument('--lang=en-US')
                chrome_options.add_argument(
                    f"--user-agent={user_agent}")
                chrome_options.add_argument("--origin=https://twitcasting.tv")
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
                driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                break
            except Exception as webdriverException:
                print(webdriverException)
            try:
                # add user-agent and origin to the command-line argument to avoid 502 errors
                # Set firefox useragent using profile rather than options
                from selenium.webdriver.firefox.service import Service
                from webdriver_manager.firefox import GeckoDriverManager
                firefox_options = webdriver.FirefoxOptions()
                # firefox_options.headless = True
                firefox_options.add_argument("--headless")
                # Update user agent if bad request 400 when downloading m3u8
                firefox_options.set_preference("media.volume_scale", "0.0")
                firefox_options.set_preference('intl.accept_languages', 'en-GB')
                firefox_options.set_preference("general.useragent.override",
                                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
                firefox_options.add_argument("--origin=https://twitcasting.tv")
                driver = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=firefox_options)
                print('Using Firefox Driver')
                break
            except Exception as webdriverException:
                print(webdriverException)
            try:
                from selenium.webdriver.edge.options import Options
                from webdriver_manager.microsoft import EdgeChromiumDriverManager
                # add user-agent and origin to the command-line argument to avoid 502 errors
                opts = Options()
                opts.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0")
                opts.add_argument("Origin: https://twitcasting.tv")
                driver = webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()), options=opts)
                print('Using Edge Driver')
                break
            except Exception as webdriverException:
                print(webdriverException)
            try:
                from selenium.webdriver.opera.options import Options
                from webdriver_manager.opera import OperaDriverManager
                # add user-agent and origin to the command-line argument to avoid 502 errors
                opts = Options()
                opts.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36")
                opts.add_argument("Origin: https://twitcasting.tv")
                driver = webdriver.Opera(service=Service(OperaDriverManager().install()), options=opts)
                print('Using Safari Driver')
                break
            except Exception as webdriverException:
                print(traceback.format_exc())
                sys.exit(webdriverException)
    except webdriver or Keys as importException:
        sys.exit(str(importException) + "\nError importing")
    return driver, WebDriverWait, EC, By


# Set up the soup and return it while requiring a link as an argument
def soupSetup(cleanLink, cookies, session):
    try:
        url = cleanLink
    except Exception:
        sys.exit("Invalid URL")
    headers = {
        'User-Agent': f'{user_agent}',
        'Origin': 'https://twitcasting.tv'}
    req = session.get(url, headers=headers, cookies=cookies)
    bSoup = BeautifulSoup(req.text, "html.parser")
    return bSoup


# Takes -l argument and "sanitize" url
# If link doesn't end with /show or /showclips then invalid link
# Returns the "sanitized" url
def linkCleanUp(argLink, cookies):
    cleanLink = None
    if (argLink is not None):
        url = argLink
    else:
        url = input("URL: ")
    # Download m3u8 link if provided
    downloadM3u8(url, cookies)
    # Take a look at this if statement back in master branch
    if "https://" not in url and "http://" not in url:
        url = "https://" + url
    if "/showclips" in url:
        cleanLink = url.split("/showclips")[0]
        cleanLink = cleanLink + "/showclips/"
        filterType = "showclips"
        return cleanLink, filterType
    elif "/show" in url:
        cleanLink = url.split("/show")[0]
        cleanLink = cleanLink + "/show/"
        filterType = "show"
        return cleanLink, filterType
    elif "/archive" in url:
        cleanLink = url.split("/archive")[0]
        cleanLink = cleanLink + "/archive/"
        filterType = "archive"
        return cleanLink, filterType
    # pattern is movie/[numbers]
    moviePattern = re.compile(r'movie/\d+')
    if "twitcasting.tv/" in url and moviePattern.findall(url) is []:
        if url.rindex("/") == len(url) - 1:
            cleanLink = url + "show/"
            return cleanLink, "show"
        else:
            cleanLink = url + "/show/"
            return cleanLink, "show"
    # pattern example: [('https', '://twitcasting.tv/', 'natsuiromatsuri', '/movie/661406762')]
    moviePattern = re.compile(r'(https|http)(://twitcasting.tv/)(.*?)(/movie/\d+)')
    regMatchList = moviePattern.findall(url)
    try:
        if (len(regMatchList[0]) == 4):
            cleanLink = url
            return cleanLink, None
    except:
        sys.exit("Invalid Link")
    return cleanLink, None


# Function takes index.m3u8 link and downloads it in cwd as {video_id}.mp4 and then exits
def downloadM3u8(m3u8, cookies):
    # Check if its an m3u8 link
    # https://dl01.twitcasting.tv/tc.vod/v/674030808.0.2-1618443661-1618472461-4ec6dd13-901d44e31383a107/fmp4/index.m3u8
    moviePattern = re.compile(r'(https|http)(:\/\/.*\.)(twitcasting\.tv\/tc\.vod\/v\/)(\d+)(.*)(\/fmp4\/index\.m3u8)$')
    regMatchList = moviePattern.findall(m3u8)
    if len(regMatchList) > 0:
        video_id = regMatchList[0][3]
        download_dir = os.getcwd()
        # Use -re, -user_agent, and -headers to set x1 read speed and avoid 502 error
        # Use -n to avoid overwriting files and then avoid re-encoding by using copy
        ffmpeg_list = ['ffmpeg', '-v', 'quiet', '-stats', '-re', '-user_agent',
                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                       '-headers', "Origin: https://twitcasting.tv"]
        if cookies != {}:
            ffmpeg_list += ['-headers', f"Cookie: 'tc_id'={cookies['tc_id']}; tc_ss={cookies['tc_ss']}"]
        ffmpeg_list += ['-n', '-i', m3u8, '-c:v', 'copy', '-c:a', 'copy', '-movflags', '+faststart']
        ffmpeg_list += [f'{download_dir}\\{video_id}.mp4']
        try:
            print("Downloading from index.m3u8\n")
            subprocess.run(ffmpeg_list, check=True)
        except Exception:
            sys.exit("Error executing ffmpeg")
        print("\nExecuted")
        sys.exit("\nDownloaded Successfully")


# Function takes in two arguments: the base link and page number
# Returns a new link by contacting base link and page number
def updateLink(baseLink, pageNumber):
    baseLink = baseLink
    updatedLink = baseLink + str(pageNumber)
    return updatedLink


# Function takes in a directory path argument
# Returns user specified directory path, else a default path is provided
def getDirectory(argOutput):
    if (argOutput is not None):
        directoryPath = "".join(argOutput)
        print("Directory Path: " + directoryPath)
    else:
        directoryPath = os.getcwd()
    return directoryPath


# Function takes in 3 arguments: soup, sanitized link, and user input file name
# Returns a proper filename for the txt file based on user input
def getFileName(soup, cleanLink, argName):
    # Add special character exception
    if (argName is not None):
        # Check if the argName contains illegal characters
        joinedName = checkFileName(argName)

        if (".txt" not in joinedName and isinstance(joinedName, list)):
            fileName = joinedName.append(".txt")
        if (".txt" not in joinedName):
            fileName = joinedName + ".txt"
        else:
            fileName = joinedName
    else:
        channelName = soup.find(class_="tw-user-nav-name").text
        channelName = checkFileName(channelName)
        if ("/showclips" in cleanLink):
            fileName = channelName.strip() + "_showclips.txt"
            return fileName
        elif ("/show" in cleanLink):
            fileName = channelName.strip() + "_shows.txt"
            return fileName
        else:
            fileName = channelName.strip() + "_urls.txt"
            return fileName
    fileName = "".join(fileName)
    return fileName


def getArchive(archiveArg):
    archiveExist = False
    currentDirectory = os.getcwd()
    try:
        if archiveArg is not None:
            archivePath = "".join(archiveArg)
            if not archiveArg.endswith(".txt"):
                archiveArg = archiveArg + ".txt"
            print("Archive Path: " + archivePath)
        else:
            archivePath = currentDirectory
    except Exception as exception:
        print(str(exception) + "\nError, creating archive.txt file in current working directory")
        archivePath = currentDirectory
    if os.path.isfile(archivePath) or os.path.isfile(str(currentDirectory) + "\\" + archiveArg):
        archiveExist = True
    return archivePath, archiveExist


def getCookies(cookie_file):
    cookies = {}
    regex = ".*(tc_id|tc_ss)\s(.*)"
    try:
        with open(cookie_file, 'r') as cf:
            for line in cf:
                match = re.search(string=line, pattern=regex)
                if match is not None:
                    cookies[match.group(1)] = match.group(2)
        if len(cookies) < 2:
            sys.exit("Error configuring the cookie file. Note cookie file must contain tc_id and tc_ss keys")
    except FileNotFoundError:
        sys.exit("Can not find cookie file")
    return cookies


# Function takes in the file name and check if it exists
# If the file exists, then remove it(replace the file)
def checkFile(fileName):
    if (os.path.isfile(fileName)):
        os.remove(fileName)


# Function takes in the file name and check if it contains illegal characters
# If it contains an illegal character then remove it and return the new file name without the illegal character
def checkFileName(fileName):
    invalidName = re.compile(r"[\\*?<>:\"/\|]")
    newFileName = fileName
    if re.search(invalidName, fileName) is not None:
        newFileName = re.sub(invalidName, "_", fileName)
        # print("\nInvalid File Name Detected\nNew File Name: " + newFileName)
    # If file name has multiple lines then join them together(because stripping newline doesn't work)
    if "\n" in newFileName:
        title_array = newFileName.splitlines()
        newFileName = " ".join(title_array)
    return newFileName


# Function that takes in foldername and create dir if it doesn't exist(used for batch downloading)
# No longer used since user will provide folder name
def createFolder(folderName):
    folderName = checkFileName(folderName)
    if os.path.isdir(folderName) is False:
        os.mkdir(folderName)


# Function that takes in two arguments: soup, and a filter of "show" or "showclips"
# Find the total page and gets the total link available to be scraped
# Returns a list that holds the total pages and total url available to be scraped
def urlCount(soup, filter):
    pagingClass = soup.find(class_="tw-pager")
    pagingChildren = pagingClass.findChildren()
    totalPages = pagingChildren[len(pagingChildren) - 1].text
    print("Total Pages: " + totalPages)

    if ("showclips" in filter):
        btnFilter = soup.find_all("a", class_="btn")
        clipFilter = btnFilter[1]
        clipBtn = clipFilter.text
        totalUrl = clipBtn.replace("Clip ", "").replace("(", "").replace(")", "")
        print("Total Links: " + totalUrl)
        return [totalPages, totalUrl]
    else:
        countLive = soup.find(class_="tw-user-nav-list-count")
        totalUrl = countLive.text
        print("Total Links: " + totalUrl)
        return [totalPages, totalUrl]


# Function that gets all the m3u8 url(since the page can contain more than one video)
# cleans it up and then return it along with membership status
def m3u8_scrape(link, cookies, session):
    soup = soupSetup(link, cookies, session)
    video_list = []
    m3u8_url = []
    membership_status = False
    print(f"\nFinding m3u8 url in {link}")
    try:
        # Finds the tag that contains the url
        video_tag = soup.find(class_="video-js")["data-movie-playlist"]
        # base64 does not contain quote
        if '"' not in video_tag:
            # Reverse string and decode base64
            video_tag = base64.b64decode(video_tag[::-1]).decode('utf-8')
        membership_status = True if soup.find(id="groupinfolink") is not None else False
        if membership_status:
            print("Member's Only Video")
        # Turns the tag string to a dict and then cleans it up
        video_dict = json.loads(video_tag)
        print(f"Found {len(video_dict)} m3u8 urls")
        for video in video_dict['2']:
            source_url = video["source"]["url"]
            m3u8_url.append(source_url.replace("\\", ""))
            print("m3u8 link: " + source_url)
        video_list.append(m3u8_url)
        video_list.append(membership_status)
    except Exception:
        print("Private Video")
        video_list.append(None)
        video_list.append(membership_status)
    return video_list


# Function takes three arguments: the file name, soup, and boolean value batch
# Scrapes the video title and url and then write it into a txt file
# Returns the number of video url extracted for that page
def linkScrape(fileName, soup, batch, passcode_list, cookies):
    session = requests.Session()
    video_list = []
    domainName = "https://twitcasting.tv"
    linksExtracted = 0
    with open(fileName, 'a', newline='') as txt_file:
        # If it's just one link scrape
        if not batch:
            print("Links: " + "1")
            m3u8_link, membership_status = m3u8_scrape(soup, cookies, session)
            if len(m3u8_link) != 0:
                linksExtracted = linksExtracted + 1
                txt_file.write(m3u8_link)
        # If it's a channel scrape
        else:
            # find all video url
            url_list = soup.find_all("a", class_="tw-movie-thumbnail")
            # find all tag containing video title
            title_list = soup.find_all("span", class_="tw-movie-thumbnail-title")
            # find all tag containing date/time
            date_list = soup.find_all("time", class_="tw-movie-thumbnail-date")

            print("Links: " + str(len(url_list)))
            # add all video url to video list
            for link in url_list:
                video_list.append(domainName + link["href"])
            # loops through the link and title list in parallel
            for link, title, date in zip(video_list, title_list, date_list):
                m3u8_link, membership_status = m3u8_scrape(link, cookies, session)
                # check to see if there are any m3u8 links
                if len(m3u8_link) != 0:
                    try:
                        date = date.text.strip()
                        video_date = re.search('(\d{4})/(\d{2})/(\d{2})', date)
                        day_date = video_date.group(3)
                        month_date = video_date.group(2)
                        year_date = video_date.group(1)
                    except:
                        exit("Error getting dates")
                    # Only write title if src isn't in the tag
                    # Meaning it's not a private video title
                    if not title.has_attr('src'):
                        full_date = "#" + year_date + month_date + day_date + " - "
                        title = [title.text.strip()]
                        title.insert(0, full_date)
                        title = "".join(title)
                        print("Title: " + title)
                    linksExtracted = linksExtracted + 1
                    txt_file.write(m3u8_link + "\n")
                else:
                    print("Error can't find m3u8 links")
    return linksExtracted, video_list


# Function takes four arguments: soup, directory path, boolean value batch, and the channel link
# Scrapes for video info
# And then calls ffmpeg to download the stream
# Returns the number of video url extracted for that page
def linkDownload(soup, directoryPath, batch, channelLink, passcode_list, archive_info, cookies):
    video_list = []
    m3u8_link = []
    domainName = "https://twitcasting.tv"
    linksExtracted = 0
    curr_dir = directoryPath
    archivePath = archive_info[0]
    archiveExist = archive_info[1]
    m3u8_url = []
    txt_format = 'w'
    session = requests.Session()
    # Batch download
    if batch:
        # Maybe consider separating extractor from downloader
        # find all video url
        url_list = soup.find_all("a", class_="tw-movie-thumbnail")
        # get channel name
        channel_name = soup.find("span", class_="tw-user-nav-name").text.strip()
        # find all tag containing video title
        title_list = soup.find_all("span", class_="tw-movie-thumbnail-title")
        # find all tag containing date/time
        try:
            date_list = soup.find_all(class_="tw-movie-thumbnail-date")
        except:
            # When the class "tw-movie-thumbnail-date", can't be found due to perhaps newly uploaded video or 1st video
            date_list = soup.find_all("time")

        # Creates folder name based on channel name
        # createFolder(channel_name)
        # download_dir = curr_dir + "\\" + checkFileName(channel_name)

        download_dir = curr_dir

        # add all video url to video list
        for link in url_list:
            video_list.append(domainName + link["href"])

        # loops through the link and title list in parallel
        for link, title, date in zip(video_list, title_list, date_list):
            try:
                txt_list = []
                # If there is an archive file path set to append mode and if not set to write mode
                if archivePath is not None:
                    if archiveExist:
                        txt_format = 'a'
                        # List index out of range error when theres extra/less space
                        # Get all the links in the file and append into txt_list array
                        with open(archivePath, 'r', newline="") as txt_file:
                            for line in txt_file:
                                txt_list.append(line.rstrip())
                        # Check if the link is in the archive txt_list array and if so skip the download
                        if link in txt_list:
                            continue
                    else:
                        txt_format = 'w'
            except Exception as archiveException:
                sys.exit(str(archiveException) + "\n Error occurred creating an archive file")

            # If there is more than 1 password and it's a private video
            if len(passcode_list) >= 1 and len(title.contents) == 3:
                # Setup selenium
                webDriver = webDriverSetup()
                driver = webDriver[0]
                WebDriverWait = webDriver[1]
                EC = webDriver[2]
                By = webDriver[3]

                try:
                    driver.get(link)
                except Exception as getLinkException:
                    sys.exit(getLinkException)

                # Find the password field element on the page
                password_element = WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input[name='password']")))

                # While the password element field remains and correct password hasn't been entered
                current_passcode = None
                while len(password_element) > 0:
                    password_element = WebDriverWait(driver, 15).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input[name='password']")))
                    # Go through all the passcode until the password element field is gone
                    for passcode in passcode_list:
                        current_passcode = passcode
                        password_element = WebDriverWait(driver, 15).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input[name='password']")))
                        password_element[0].send_keys(passcode)
                        # If send_keys doesn't send the password then try clicking the send button
                        try:
                            button_element = WebDriverWait(driver, 15).until(
                                EC.presence_of_all_elements_located((By.CLASS_NAME, "tw-button-secondary.tw-button-small")))
                            button_element[0].click()
                        except:
                            pass
                        # If the password field element remains and there are still more passcodes then try again with another passcode
                        try:
                            password_element = WebDriverWait(driver, 10).until(
                                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input[name='password']")))
                            if len(password_element) > 0:
                                continue
                        except:
                            break
                    # If after checking all the passcode and it's still locked then break out the while loop and move on to another video
                    if len(password_element) >= 0:
                        break

                # Try to find the video element
                try:
                    m3u8_tag_element = WebDriverWait(driver, 15).until(
                        EC.presence_of_all_elements_located((By.CLASS_NAME, "video-js")))
                    # If video element is found then get the m3u8 url
                    if len(m3u8_tag_element) > 0:
                        m3u8_tag_dic = json.loads(m3u8_tag_element[0].get_attribute("data-movie-playlist"))
                        for m3u8_tag in m3u8_tag_dic['2']:
                            source_url = m3u8_tag["source"]["url"]
                            m3u8_url.append(source_url.replace("\\", ""))
                            # prob not needed idr
                            m3u8_link = m3u8_url
                            # If a passcode was used/set then remove it from the passcode_list
                            # Helps speeds up entering the passcode by removing used passcode
                            if current_passcode is not None:
                                passcode_list.remove(current_passcode)
                            driver.quit()
                except Exception as noElement:
                    print("Can't find private m3u8 tag,", str(noElement), "It may be a protected stream")
                    driver.quit()

            # Send m3u8 url and ensure it's a valid m3u8 link
            try:
                m3u8_link, membership_status = m3u8_scrape(link, cookies, session)
                if membership_status and "\\【Member Video】" not in download_dir:
                    download_dir = download_dir + "\\【Member Video】"
                elif not membership_status:
                    download_dir = download_dir.replace("\\【Member Video】", "")
            except ValueError:
                continue

            if m3u8_link is None or len(m3u8_link) == 0:
                m3u8_link = m3u8_url

            # check to see if there are any m3u8 links
            if len(m3u8_link) != 0:
                # Use regex to get year, month, and day
                try:
                    date = date.text.strip()
                    # Find date of the video in year/month/day
                    video_date = re.search('(\d{4})/(\d{2})/(\d{2})', date)
                    day_date = video_date.group(3)
                    month_date = video_date.group(2)
                    year_date = video_date.group(1)
                except:
                    exit("Error getting dates")
                # Loop through and download all the m3u8
                for i, m3u8 in enumerate(m3u8_link):
                    # Only write title if src isn't in the tag
                    # Meaning it's not a private video title
                    if not title.has_attr('src'):
                        full_date = year_date + month_date + day_date
                        video_title = checkFileName(title.text.strip())
                        if i == 0:
                            video_title = f"{full_date} - {video_title}"
                        else:
                            video_title = f"{full_date} - {video_title}_{i+1}"

                    # Get unique video id and append to the end of the title
                    vid_id = str(re.search("(\d+)$", link).group())
                    video_title = f"{video_title} ({vid_id})"
                    if os.path.isfile(f'{download_dir}\\{video_title}.mp4'):
                        video_title = video_title + str(i)
                    print("Title: " + str(video_title))
                    linksExtracted = linksExtracted + 1
                    # Use -re, -user_agent, and -headers to set x1 read speed and avoid 502 error
                    # Use -n to avoid overwriting files and then avoid re-encoding by using copy
                    # -c copy -bsf:a aac_adtstoasc
                    # ffmpeg_list = ['ffmpeg', '-re', '-user_agent',
                    #                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36",
                    #                '-headers', "Origin: https://twitcasting.tv"]

                    ffmpeg_list = ['ffmpeg', '-v', 'quiet', '-stats', '-user_agent', user_agent,
                                   '-headers', "Origin: https://twitcasting.tv"]
                    if cookies != {}:
                        ffmpeg_list += ['-headers', f"Cookie: 'tc_id'={cookies['tc_id']}; tc_ss={cookies['tc_ss']}"]
                    # Note split at & since cmd doesn't like it: e.g. https://dl193236.twitcasting.tv/tc.vod.v2/v1/streams/760007902.0.2/hls/master.m3u8?k=%2Ftc.vod%2Fv%2F760007902.0.2-1677557604-1677586404-f21a6f25-00d91311525594a4&spm=1
                    ffmpeg_list += ['-n', '-i', m3u8.split("&")[0], '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', '-bsf:a', 'aac_adtstoasc']
                    ffmpeg_list += [f'{download_dir}\\{video_title}.mp4']
                    # Add check for if -a is not specified but downloaded channel video already exist
                    # So check if {title} + .mp4 matches filename in that cwd
                    try:
                        subprocess.run(ffmpeg_list, check=True)
                    except subprocess.CalledProcessError:
                        sys.exit("Error executing ffmpeg")
                    print(f"\nExecuted and downloaded {i+1}/{len(m3u8_link)}")
                # Reset m3u8 link and url
                m3u8_link = []
                m3u8_url = []
                if archivePath is not None:
                    with open(archivePath, txt_format, newline='') as txt_file:
                        archiveExist = True
                        txt_file.write(link + "\n")
                        # Set appended to be true so on error this appended link can be tested and removed
                        print(f"Appended {link} to archive file\n")
            else:
                print("Error can't find m3u8 links")

    # Single link download
    else:
        try:
            # Get the unique video id
            vid_id = str(re.search("(\d+)$", channelLink).group())
        except:
            print("Could not get video id")
            pass

        # find tag containing the video name
        try:
            title = soup.find("span", class_="tw-player-page__title-editor-value").text.strip()
            title = checkFileName(title)
        except Exception as e:
            title = "temp"
        # find tag containing date/time
        try:
            date = soup.find("time", class_="tw-movie-thumbnail-date").text.strip()
        except:
            # When the class "tw-movie-thumbnail-date", can't be found due to perhaps newly uploaded video or 1st video
            date = soup.find("time").text.strip()

        # If one passcode is supplied to download one locked video
        if len(passcode_list) == 1:
            # find tag containing the video name
            try:
                title = soup.find("div", class_="tw-basic-page-single-column").find("h2").text.strip()
                title = checkFileName(title)
            except:
                title = "temp"

            # Setup selenium
            webDriver = webDriverSetup()
            driver = webDriver[0]
            WebDriverWait = webDriver[1]
            EC = webDriver[2]
            By = webDriver[3]

            try:
                driver.get(channelLink)
            except Exception as getLinkException:
                sys.exit(getLinkException)

            # Find the password field element on the page
            password_element = WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input[name='password']")))
            button_element = WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "tw-button-secondary.tw-button-small")))
            # Enter and submit the passcode
            password_element[0].send_keys(passcode_list[0])
            button_element[0].click()

            # Try to find the video element
            try:
                m3u8_tag = WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[data-movie-playlist]")))
                # If video element is found then get the m3u8 url
                if len(m3u8_tag) > 0:
                    m3u8_tag_dic = json.loads(m3u8_tag[0].get_attribute("data-movie-playlist"))
                    source_url = m3u8_tag_dic.get("2")[0].get("source").get("url")
                    m3u8_url = source_url.replace("\\", "")
                    m3u8_link = m3u8_url
                    driver.quit()
            except Exception as noElement:
                print(str(noElement) + "\nCan't find private m3u8 tag")
                driver.quit()

            #copy from else statement below
            # check to see if there are any m3u8 links
            if len(m3u8_link) != 0:
                # Use regex to get year, month, and day
                try:
                    video_date = re.search('(\d{4})/(\d{2})/(\d{2})', date)
                    day_date = video_date.group(3)
                    month_date = video_date.group(2)
                    year_date = video_date.group(1)
                except:
                    exit("Error getting dates")

                full_date = year_date + month_date + day_date
                video_title = f"{full_date} - {title} ({vid_id})"
                print("Title: ", title)
                linksExtracted = linksExtracted + 1
                download_dir = curr_dir
                # Use -re, -user_agent, and -headers to set x1 read speed and avoid 502 error
                # Use -n to avoid overwriting files and then avoid re-encoding by using copy
                # ffmpeg_list = ['ffmpeg', '-re', '-user_agent',
                #                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36",
                #                '-headers', "Origin: https://twitcasting.tv"]

                ffmpeg_list = ['ffmpeg', '-v', 'quiet', '-stats', '-user_agent', user_agent,
                               '-headers', "Origin: https://twitcasting.tv"]
                if cookies != {}:
                    ffmpeg_list += ['-headers', f"Cookie: 'tc_id'={cookies['tc_id']}; tc_ss={cookies['tc_ss']}"]
                ffmpeg_list += ['-n', '-i', m3u8_link, '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', '-bsf:a', 'aac_adtstoasc']
                ffmpeg_list += [f'{download_dir}\\{video_title}.mp4']
                try:
                    subprocess.run(ffmpeg_list, check=True)
                except subprocess.CalledProcessError:
                    sys.exit("Error executing ffmpeg")
                print("\nExecuted")
            else:
                sys.exit("Error can't find m3u8 links\n")

        else:
            m3u8_link, membership_status = m3u8_scrape(channelLink, cookies, session)
            # check to see if there are any m3u8 links
            if len(m3u8_link) != 0:
                # Use regex to get year, month, and day
                try:
                    video_date = re.search('(\d{4})/(\d{2})/(\d{2})', date)
                    day_date = video_date.group(3)
                    month_date = video_date.group(2)
                    year_date = video_date.group(1)
                except:
                    exit("Error getting dates")

                full_date = year_date + month_date + day_date

                for i, m3u8 in enumerate(m3u8_link):
                    if i == 0:
                        video_title = f"{full_date} - {title}"
                    else:
                        video_title = f"{full_date} - {title}_{i + 1}"

                    video_title = f"{video_title} ({vid_id})"
                    print("Title: ", video_title)
                    linksExtracted = linksExtracted + 1
                    download_dir = curr_dir
                    # Use -re, -user_agent, and -headers to set x1 read speed and avoid 502 error
                    # Use -n to avoid overwriting files and then avoid re-encoding by using copy
                    # ffmpeg_list = ['ffmpeg', '-re', '-user_agent',
                    #                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36",
                    #                '-headers', "Origin: https://twitcasting.tv"]

                    ffmpeg_list = ['ffmpeg', '-v', 'quiet', '-stats', '-user_agent', user_agent,
                                   '-headers', "Origin: https://twitcasting.tv"]
                    if cookies != {}:
                        ffmpeg_list += ['-headers', f"Cookie: 'tc_id'={cookies['tc_id']}; tc_ss={cookies['tc_ss']}"]
                    ffmpeg_list += ['-n', '-i', m3u8, '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', '-bsf:a', 'aac_adtstoasc']
                    ffmpeg_list += [f'{download_dir}\\{video_title}.mp4']
                    try:
                        subprocess.run(ffmpeg_list, check=True)
                    except subprocess.CalledProcessError:
                        sys.exit("Error executing ffmpeg")
                    print(f"\nExecuted and downloaded {i+1}/{len(m3u8_link)}\n")
            else:
                sys.exit("Error can't find m3u8 links\n")
    return linksExtracted, video_list


# Function that scrapes/download the entire channel or single link
# while printing out various information onto the console
def main():
    # Check for keyboard interrupt
    signal.signal(signal.SIGINT, lambda x, y: sys.exit("\nKeyboard Interrupt"))
    # Links extracted
    linksExtracted = 0
    # Get commandline arguments
    args = arguments()
    # Get cookies for membership videos
    if args.cookies:
        cookies = getCookies("".join(args.cookies))
    else:
        cookies = {}

    # Get the clean twitcast channel link
    try:
        linkCleanedUp = linkCleanUp(args.link, cookies)
        channelLink = linkCleanedUp[0]
        channelFilter = linkCleanedUp[1]
    except Exception as linkError:
        sys.exit(str(linkError) + "\nInvalid Link")

    # Check and make sure both --file and --passcode isn't specified at once
    passcode_list = []
    if args.file and args.passcode:
        sys.exit("You can not specify both --file and --passcode at the same time.\nExiting")
    # Check if --file is supplied and if so create a list of the passcode
    if args.file:
        try:
            pass_file = getDirectory(args.file)
            with open(pass_file, 'r', newline='', encoding='utf-8') as txt_file:
                # csv_reader = csv.reader(csv_file)
                passcode_list = list(txt_file)
        except Exception as f:
            sys.exit(str(f) + "\nError occurred when opening passcode file")
    # Check if --passcode is specified and if it is set the passcode to a passcode_list
    if args.passcode:
        passcode_list = [args.passcode]
    if args.archive:
        archive_info = getArchive(args.archive)
    else:
        archive_info = [None, False]

    # Set up beautifulsoup
    session = requests.Session()
    soup = soupSetup(channelLink, cookies, session)
    # Get the filename
    fileName = getFileName(soup, channelLink, args.name)

    # Get the directory path
    directoryPath = getDirectory(args.output)

    # Set the directory path
    try:
        # Check if current directory exist and if not created it recursively
        Path(directoryPath).mkdir(parents=True, exist_ok=True)

        if isinstance(directoryPath, list):
            os.chdir(os.path.abspath(directoryPath[0]))
        else:
            os.chdir(os.path.abspath(directoryPath))
    except Exception as e:
        # sys.exit("Error setting output directory")
        sys.exit(str(e), "\nError setting output directory")
    # Check if the file exist and if it does delete it
    checkFile(fileName)

    # Count the total pages and links to be scraped
    # If it's a batch download/scrape set to true
    batch = channelFilter is not None
    # Initiate batch download or scrape
    if batch:
        countList = urlCount(soup, channelFilter)
        totalPages = countList[0]
        totalLinks = countList[1]

        if args.scrape:
            print("Filename: " + fileName)
        for currentPage in range(int(totalPages)):
            if (currentPage == int(totalPages)):
                print("\nPage: " + str(currentPage - 1))
            else:
                print("\nPage: " + str(currentPage + 1))
            if (currentPage != 0):
                updatedLink = updateLink(channelLink, currentPage)
                soup = soupSetup(updatedLink, cookies, session)
            # If --scrape is not specified then download video else just scrape
            if not args.scrape:
                linksExtracted += linkDownload(soup, directoryPath, batch, channelLink, passcode_list, archive_info, cookies)[0]
                if batch:
                    print("\nTotal Links Extracted: " + str(linksExtracted) + "/" + totalLinks + "\nExiting")
                else:
                    sys.exit("\nTotal Links Extracted: " + str(linksExtracted) + "/" + "1" + "\nExiting")

            else:
                linksExtracted += linkScrape(fileName, soup, batch, passcode_list, cookies)[0]
                if batch:
                    print("\nTotal Links Extracted: " + str(linksExtracted) + "/" + totalLinks + "\nExiting")
                else:
                    print("\nTotal Links Extracted: " + str(linksExtracted) + "/" + "1" + "\nExiting")
    # Initiate single download or scrape
    else:
        if not args.scrape:
            linksExtracted += linkDownload(soup, directoryPath, batch, channelLink, passcode_list, archive_info, cookies)[0]
            print("\nTotal Links Extracted: " + str(linksExtracted) + "/" + "1" + "\nExiting")
        else:
            linksExtracted += linkScrape(fileName, channelLink, batch, passcode_list, cookies)[0]
            print("\nTotal Links Extracted: " + str(linksExtracted) + "/" + "1" + "\nExiting")


if __name__ == '__main__':
    try:
        main()
        for filename in os.listdir(os.getcwd()):
            if filename.endswith(".mp4"):
                originalFilename = filename.split(".mp4")[0]
                os.system(
                    f'ffmpeg -i "{filename}" -c:a libopus "{originalFilename}.opus"'
                )
                print(f"{filename} has been sent to the trash can")
                send2trash.send2trash(filename)
            else:
                continue
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        # sys.exit(str(e) + "\nUnexpected Error")
        traceback.print_exc()
