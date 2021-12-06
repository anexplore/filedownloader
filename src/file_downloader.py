# -*- coding: utf-8 -*-
import concurrent.futures
import os.path
import queue
import sys
import threading
import traceback

import requests

# LOG QUIET
QUIET = False


def be_quiet():
    global QUIET
    QUIET = True


def std_log(string):
    global QUIET
    if not QUIET:
        sys.stdout.write('[%s-%s] %s\n' % (threading.current_thread().name, threading.current_thread().ident, string))
        sys.stdout.flush()


def create_empty_fix_size_binary_file(path, size, mode='wb', overwrite_if_already_exists=False):
    """
    创建指定大小空白文件
    :param path: 文件路径
    :param size: 文件大小
    :param mode: 文件模式
    :param overwrite_if_already_exists: 当文件存在是是否覆盖
    """
    if size < 0 or not path:
        raise Exception('path must not empty and file size must be bigger than zero')
    if not mode:
        mode = 'wb'
    if not overwrite_if_already_exists and os.path.exists(path):
        raise Exception('path already exists')
    open_file = open(path, mode)
    open_file.truncate(size)
    open_file.close()


def is_support_multi_range(headers):
    """
    是否包含accept-ranges 头
    :param headers: request.response.headers
    :return: true or false
    """
    return headers.get('Accept-Ranges', '').strip() == 'bytes'


def get_content_length(headers):
    return int(headers.get('Content-Length', -1))


def read_all_finished_segment_list(segment_list_file):
    """
    读取文件下载成功段记录
    :param segment_list_file: segment list file
    :return: data_length, segment_list(merged)
    """
    with open(segment_list_file, 'r') as fd:
        lines = [line.strip() for line in fd]
        if not lines:
            return None, None
        data_length = int(lines[0])
        # (0, 10), (11, 20), (11, 20), (12, 15), (9, 12)
        segments = [line.split(',') for line in lines[1:] if line != '']
        segments = [[int(start), int(end)] for start, end in segments]
        # sort by start and  merge
        sorted_segments = sorted(segments, key=lambda se: se[0])
        merged_segments = []
        prev = None
        for segment in sorted_segments:
            if len(segment) != 2:
                continue
            if prev is None:
                prev = segment
                continue
            if segment[0] <= prev[1] or segment[0] == prev[1] + 1:
                prev = [prev[0], max(segment[1], prev[1])]
            else:
                merged_segments.append(prev)
                prev = segment
        if prev is not None:
            merged_segments.append(prev)
        return data_length, merged_segments


def find_holes(data_length, merged_segment_list):
    """
    找到文件空洞部分
    :param data_length: 数据长度
    :param merged_segment_list: 无区间重合的段列表
    :return: segment list
    """
    # [0, data_length - 1]
    # sort segment
    sorted_segment_list = sorted(merged_segment_list, key=lambda se : se[0])
    filled_index = 0
    segments = []
    for segment in sorted_segment_list:
        if segment[0] == filled_index:
            filled_index = segment[1] + 1
        elif segment[0] > filled_index:
            # hole
            segments.append([filled_index, segment[0] - 1])
            filled_index = segment[1] + 1
        else:
            raise RuntimeError('segment %s-%s overflow fill index %s' % (segment[0], segment[1], filled_index))
    if filled_index < data_length:
        segments.append([filled_index, data_length - 1])
    return segments


class OverWriteException(Exception):
    """重复覆盖写"""
    pass


class FetchHeaderException(Exception):
    """获取请求响应头错误"""
    pass


class SegmentDownloader(object):
    """
    段下载器
    path: 数据写入地址
    raw_request: 原始请求
    range_start: Range 开始字节
    range_end: Range 结束字节 这里对方服务不一定能够返回到达range_end的数据 如果range_end <= 0表示全文件下载不分段
    range_rel_end: 服务器返回的数据真实end位置
    request_args: HTTP请求的其它控制参数
    """
    def __init__(self, path: str, request: requests.Request, range_start: int, range_end: int, **request_args):
        self.path = path
        self.raw_request = request
        self.range_start = range_start
        self.range_end = range_end
        self.range_real_end = -1
        self._segment_writer = None
        self.request_args = {}
        self.request_args.update(request_args)

    def total_downloaded_data_length(self):
        """
        :return: 下载回来的数据长度
        """
        if self.range_real_end < self.range_start:
            return 0
        return self.range_real_end - self.range_start + 1

    def download(self):
        try:
            self._segment_writer = SegmentWriter(self.path,
                                                 self.range_start,
                                                 0 if self.range_end <= 0 else (self.range_end - self.range_start + 1)
                                                 )
            with requests.Session() as session:
                req = self.raw_request.prepare()
                if self.range_end > 0:
                    req.headers['Range'] = 'bytes=%s-%s' % (self.range_start, self.range_end)
                self.request_args['stream'] = True
                with session.send(req, **self.request_args) as res:
                    content_range = res.headers.get('Content-Range')
                    std_log('start request for range %s' % content_range)
                    for chunk in res.iter_content(chunk_size=8192):
                        if chunk is None:
                            break
                        chunk_size = len(chunk)
                        # 如果返回的数据比预设的数据要多 那么截断 不继续下载
                        if self.range_end > 0 and chunk_size > self._segment_writer.left_capacity():
                            self._segment_writer.write(chunk[:self._segment_writer.left_capacity()])
                            break
                        else:
                            self._segment_writer.write(chunk)
                self.range_real_end = self.range_start + self._segment_writer.total_write_data_length() - 1
        finally:
            if self._segment_writer:
                self._segment_writer.close()
            std_log('finish range %s-%s' % (self.range_start, self.range_real_end))


class SegmentWriter(object):
    """
    将数据接写入文件的指定数据段中
    path: 文件目录
    seek_offset: 文件写入的初始offset
    length: 需要写入的数据长度 如果小于等于0 则标识从seek_offset开始追加往后写并不控制大小
    """
    def __init__(self, path, seek_offset, length):
        self.writer = open(path, 'r+b')
        self.writer.seek(seek_offset)
        self.seek_offset = seek_offset
        self.offset = seek_offset
        self.length = length
        self.limit = 0 if self.length <= 0 else (self.offset + length - 1)

    def write(self, data):
        if data is None:
            return
        if self.length > 0 and self.offset + len(data) - 1 > self.limit:
            raise OverWriteException('write to much data, cur offset %s, limit %s, prepare to write data length %s' %
                               (self.offset, self.limit, len(data)))
        self.writer.write(data)
        self.writer.flush()
        self.offset = self.writer.tell()

    def total_write_data_length(self):
        """已经写入的总数据长度"""
        return self.offset - self.seek_offset

    def left_capacity(self):
        """剩余可写空间 如果0表示不限制"""
        return 0 if self.limit == 0 else (self.limit - self.offset + 1)

    def close(self):
        self.writer.close()


class DownloaderCoordinator(object):
    """
    分段下载协调器
    发送请求判定是否支持分段下载
    制定下载计划
    byte缺失段查漏补缺
    path: 文件存储路径
    request: requests请求
    request_ctl_args: 请求其它参数 比如 timeout proxies 等
    max_thread: 最大线程数
    force_segment: 是否强制分段下载
    segment_size: 每段大小
    max_error_retry: 最段大重试下载次数
    finished_segment_file: 用来存储已经完成的段 data_length \n segment[start, end] \n segment \n ...
    """

    def __init__(self, path: str, request: requests.Request, request_ctl_args: dict, max_thread: int = 5,
                 force_segment: bool = True,
                 segment_size: int = 5 * 1024 * 1024,
                 max_error_retry:int = 10,
                 finished_segment_file=None):
        self.path = path
        self.request = request
        self.request_ctl_args = request_ctl_args
        if self.request_ctl_args is None:
            self.request_ctl_args = {}
        self.max_thread = max_thread
        self.segment_size = segment_size
        self.force_segment = force_segment
        self.max_error_retry = max_error_retry
        self.finished_segment_file = finished_segment_file
        self._thread_count = 1
        self._data_length = 1
        self._finished_length = 0
        self._finished_thread_count = 0
        self._future = None
        self._failed_segment_list = []
        self._lock = threading.Lock()

    def _increment_and_get(self, length):
        with self._lock:
            self._finished_length += length
            return self._finished_length

    def _record_failed_segment(self, start, end):
        with self._lock:
            self._failed_segment_list.append((start, end))

    def _record_finished_segment(self, start, end):
        with self._lock:
            if self.finished_segment_file:
                with open(self.finished_segment_file, 'a+') as fd:
                    fd.write('%s,%s\n' % (start, end))

    def _record_data_length(self, data_length):
        with self._lock:
            if self.finished_segment_file:
                with open(self.finished_segment_file, 'w') as fd:
                    fd.write('%s\n' % data_length)

    def _record_finish_thread_count(self):
        with self._lock:
            self._finished_thread_count += 1
            if self._thread_count == self._finished_thread_count and self._future:
                self._future.set_result(True)

    def get_all_failed_segment(self):
        """获取到所有失败的段区间列表"""
        with self._lock:
            return self._failed_segment_list[:]

    def _start(self, from_breakpoint=False, data_length=None, breakpoint_segment_list=None):
        self.request_ctl_args['stream'] = True
        task_queue = queue.Queue()
        try_to_segment = True
        if not from_breakpoint:
            # 第一步 请求 并 判定是否支持分段
            prepared_request = self.request.prepare()
            session = requests.Session()
            try:
                response = session.send(prepared_request, **self.request_ctl_args)
                response.close()
            except Exception as error:
                raise FetchHeaderException(error)
            self._data_length = get_content_length(response.headers)
            self._record_data_length(self._data_length)
            try_to_segment = is_support_multi_range(response.headers)
            # 创建空文件
            create_empty_fix_size_binary_file(self.path, 0 if self._data_length < 0 else self._data_length)
        else:
            self._data_length = data_length
        if self.force_segment:
            try_to_segment = True
        if from_breakpoint:
            # 修正_finished_length
            self._finished_length = self._data_length
            # 切分大段
            for segment in breakpoint_segment_list:
                offset = segment[0]
                self._finished_length -= (segment[1] - segment[0] + 1)
                while offset <= segment[1]:
                    task = (offset, min(offset + self.segment_size - 1, segment[1]))
                    offset += self.segment_size
                    task_queue.put(task)
        else:
            # 从0开始分段
            if try_to_segment and self._data_length > self.segment_size:
                offset = 0
                while offset < self._data_length:
                    task = (offset, min(offset + self.segment_size - 1, self._data_length - 1))
                    offset += self.segment_size
                    task_queue.put(task)
            else:
                task_queue.put((0, 0))
        self._thread_count = min(task_queue.qsize(), self.max_thread)
        for work_index in range(self._thread_count):
            work_thread = threading.Thread(name='work-%s' % work_index,
                                           target=self._work_wrapper,
                                           args=(task_queue,))
            work_thread.start()

    def start(self, from_breakpoint=False, data_length=None, breakpoint_segment_list=None):
        """
        开启下载
        :param from_breakpoint: 断点续传
        :param data_length: 数据总长度
        :param breakpoint_segment_list: 断点时的未完成的segment list
        :return: Future
        """
        self._future = concurrent.futures.Future()
        self._future.set_running_or_notify_cancel()
        try:
            self._start(from_breakpoint=from_breakpoint,
                        data_length=data_length,
                        breakpoint_segment_list=breakpoint_segment_list
                        )
        except Exception as error:
            self._future.set_exception(error)
        finally:
            return self._future

    def _work_wrapper(self, task_queue):
        try:
            self._work(task_queue)
        finally:
            self._record_finish_thread_count()

    def _work(self, task_queue):
        while True:
            try:
                # [start, end]
                task = task_queue.get(timeout=1)
            except queue.Empty:
                break
            retry = 0
            while True:
                if retry > self.max_error_retry:
                    std_log('segment download failed times exceed max retry time %s' % self.max_error_retry)
                    self._record_failed_segment(task[0], task[1])
                    break
                downloader = SegmentDownloader(self.path, self.request, task[0], task[1], **self.request_ctl_args)
                try:
                    downloader.download()
                except Exception as error:
                    std_log('download worker occurs error and retry, %s' % traceback.format_exc())
                    retry += 1
                    continue
                retry = 0
                # 从头下载到尾部
                if task[0] == 0 and task[1] == 0:
                    break
                finished_length = self._increment_and_get(downloader.total_downloaded_data_length())
                std_log('=====finish percent %s=====' % (finished_length / self._data_length))
                if downloader.range_real_end == task[1]:
                    # 正常区间全部下载完毕
                    self._record_finished_segment(task[0], task[1])
                    break
                elif downloader.range_real_end < task[1]:
                    # 区间下载出现错误 继续补充下载
                    self._record_finished_segment(task[0], downloader.range_real_end)
                    task = (downloader.range_real_end + 1, task[1])
                else:
                    raise RuntimeError('range real end is exceed expected value')


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('url', type=str, help='http url')
    parser.add_argument('file', type=str, help='save file path')
    parser.add_argument('-b', '--breakpoint', default=False, action='store_true', help='from breakpoint')
    parser.add_argument('-bf', '--breakpoint_file', type=str, help='break point file')
    parser.add_argument('-d', '--data', type=str, help='post data')
    parser.add_argument('-ds', '--disable_segment', default=False, action='store_true')
    parser.add_argument('-H', '--header', type=str, action='append', help='http header')
    parser.add_argument('-m', '--method', type=str, help='http method')
    parser.add_argument('-mr', '--max_error_retry', type=str, default=10, help='max error retry')
    parser.add_argument('-p', '--proxy', type=str, help='http proxy')
    parser.add_argument('-t', '--timeout', type=int, default=60, help='timeout')
    parser.add_argument('-T', '--thread', type=int, default=5, help='download thread number')
    parser.add_argument('-s', '--size', type=int, default=5*1024*1024, help='segment size')
    return parser.parse_args()


def prepare_parameters():
    args = parse_args()
    method = 'GET' if not args.method else args.method
    headers = {}
    data = args.data
    ctl_args = {}
    if args.proxy:
        ctl_args['proxies'] = {
            'http': args.proxy,
            'https': args.proxy
        }
    ctl_args['timeout'] = args.timeout
    if args.header:
        for header in args.header:
            key, value = header.split(':', maxsplit=2)
            headers[key] = value
    request = requests.Request(
        method=method,
        url=args.url,
        headers=headers,
        data=data
    )
    return request, ctl_args, args


def download_file():
    request, ctl_args, args = prepare_parameters()
    downloader = DownloaderCoordinator(args.file, request, ctl_args,
                                       max_thread=args.thread,
                                       force_segment=not args.disable_segment,
                                       max_error_retry=args.max_error_retry,
                                       finished_segment_file=args.breakpoint_file)
    if args.breakpoint:
        std_log('will start from breakpoint file')
        data_length, segments = read_all_finished_segment_list(args.breakpoint_file)
        segment_holes = find_holes(data_length, segments)
        if not segment_holes:
            std_log('all file segment is already downloaded')
            return
        future = downloader.start(True, data_length, segment_holes)
    else:
        std_log('start to download')
        future = downloader.start(False)
    future.result()
