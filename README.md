# filedownloader
multi thread file downloader/多线程文件下载器

## intro
适用于大文件、网络时延大(但带宽充足)的情况

* 多线程分段下载
* 支持设置段大小
* 支持设置HTTP代理
* 支持断点续传

## install
~~~shell
python setup.py install
~~~
or
~~~shell
pip install file_mt_downloader
~~~

## how to use
### 1、Command Line
* 从URL下载到本地wechat.exe
~~~shell
python -m file_mt_downloader "https://dldir1.qq.com/weixin/Windows/WeChatSetup.exe" "wechat.exe"
~~~

* 断点续传
已经下载文件的一部分 异常中断 可接需下载

1、首次下载

通过break point file记录成功下载的数据段
~~~shell
python -m file_mt_downloader "target url" "save file" -bf "break point file"
~~~
2、从断开开始下载

从 break point file 读取历史下载段 计算缺失段接续下载
~~~shell
python -m file_mt_downloader "target url" "save file" -bf 'break point file' -b
~~~

### more parameters
~~~
usage: __main__.py [-h] [-b] [-bf BREAKPOINT_FILE] [-d DATA] [-ds] [-H HEADER]
                   [-m METHOD] [-mr MAX_ERROR_RETRY] [-p PROXY] [-t TIMEOUT]
                   [-T THREAD] [-s SIZE]
                   url file

positional arguments:
  url                   http url
  file                  save file path

optional arguments:
  -h, --help            show this help message and exit
  -b, --breakpoint      from breakpoint
  -bf BREAKPOINT_FILE, --breakpoint_file BREAKPOINT_FILE
                        break point file
  -d DATA, --data DATA  post data
  -ds, --disable_segment
  -H HEADER, --header HEADER
                        http header
  -m METHOD, --method METHOD
                        http method
  -mr MAX_ERROR_RETRY, --max_error_retry MAX_ERROR_RETRY
                        max error retry
  -p PROXY, --proxy PROXY
                        http proxy
  -t TIMEOUT, --timeout TIMEOUT
                        timeout
  -T THREAD, --thread THREAD
                        download thread number
  -s SIZE, --size SIZE  segment size
~~~

### 2、Python Script
~~~python
import requests
from file_mt_downloader import file_downloader

target_url = 'https://xxxx.xxx/xxx.exe'
save_path = 'xxx.exe'
ctl_args = {
    'timeout': 60,
    'proxies': {
        'https': 'localhost:8080',
        'http': 'localhost:8080',
    }
}
request = requests.Request(url=target_url)
downloader = file_downloader.DownloaderCoordinator(save_path, request, ctl_args)
downloader.start().result()
~~~