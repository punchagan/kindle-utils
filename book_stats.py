#!/usr/bin/env python
#
# This file is released under the GPLv2 license.
#     Copyright (C) 2012 Matt Brown <matt@mattb.net.nz>

from datetime import timedelta
import logging
import optparse
import os
import sys
import time

if sys.hexversion < 0x02070000:
    sys.exit("Python 2.7 or newer is required to run this program.")

import apnx_parser
import log_parser
import mobibook

logger = logging.getLogger().getChild('book_stats')


def FormatHMS(hms_str):
    hour, mins, secs = map(int, hms_str.split(':', 2))
    if secs > 30:
        mins += 1
    rv = []
    if hour > 0:
        rv.append('%d hour' % hour)
        if hour > 1:
            rv.append('s')
        rv.append(', ')
    rv.append('%d min' % mins)
    if mins > 1:
        rv.append('s')
    return ''.join(rv)


def PrintHMS(seconds):
    d = timedelta(seconds=seconds)
    ds = str(d)
    if ', ' not in ds:
        return FormatHMS(ds)
    else:
        days, hms = ds.split(', ')
        return '%s, %s' % (days, FormatHMS(hms))


def GetBookMetadata(asin, book_dir):
    mobi = None
    sidecar = None
    for bookfile in sorted(os.listdir(book_dir)):
        if mobi and sidecar:
            break
        if asin not in bookfile:
            continue
        filename = os.path.join(book_dir, bookfile)
        if bookfile.endswith(('.azw', '.mobi')):
            try:
                mobi = mobibook.MobiBook(open(filename, 'r'))
            except mobibook.MobiException, e:
                logger.warn('Could not read MobiBook %s for %s: %s', bookfile,
                            asin, e)
                mobi = None
        elif bookfile.endswith('.apnx'):
            try:
                sidecar = apnx_parser.ApnxFile(filename)
            except apnx_parser.ApnxException, e:
                logger.warn('Could not read page number sidecar %s for %s: %s',
                            bookfile, asin, e)
                sidecar = None
            if not sidecar.HasPageNumbers():
                logger.info('Sidecar %s for %s has no page number data!',
                        bookfile, asin)
                sidecar = None

    return mobi, sidecar


def PrintBooks(books, book_dir, only_book=None, verbose=False):
    now = time.time()
    rv = []
    events = None
    for book in books.values():
        if only_book:
            if book.asin != only_book:
                continue
            events = book.events
        reads = book.reads
        if not reads:
            rv.append((0, book.asin, book))
        else:
            newest = max([t[2] is None and now or t[2] for t in reads])
            rv.append((newest, book.asin, book))

    total_duration = 0
    eventpos = 0
    for newest, asin, book in sorted(rv, reverse=True):
        metadata, sidecar = GetBookMetadata(asin, book_dir)
        if metadata:
            title = '%s: %s' % (asin, metadata.title)
        else:
            title = asin
        reads = book.reads
        print '%s: Read % 2d times. Last Finished: %s' % (
                title, len(reads),
                newest == now and 'In Progress!' or time.ctime(newest))
        if only_book and verbose:
            print ' Length: %d' % book.length
        for start, startpos, end, endpos, duration in reads:
            if sidecar:
                start_txt = 'p%s' % sidecar.GetPageLabelForPosition(startpos)
                end_txt = 'p%s' % sidecar.GetPageLabelForPosition(endpos)
            else:
                start_txt = '@%s' % startpos
                end_txt = '@%s' % endpos
            print ' - %s => %s. Reading time %s (%s => %s)' % (
                    time.ctime(start),
                    end is None and 'In Progress!' or time.ctime(end),
                    PrintHMS(duration), start_txt, end_txt)
            total_duration += duration
            if only_book and verbose:
                # Print all events.
                for idx, event in enumerate(events[eventpos:]):
                    ts, event_type, data = event
                    if end and ts > end:
                        eventpos += idx
                        break
                    if sidecar:
                        page = sidecar.GetPageLabelForPosition(data)
                    else:
                        page = '?'
                    print '   %s on page %s/%s @ %s' % (
                            log_parser.KindleBook.EventToString(event_type),
                            page, data, time.ctime(ts))
        print ''

    if not only_book:
        print 'Read %d books in total. %s of reading time' % (
                len(rv), PrintHMS(total_duration))


def ParseOptions(args):
    parser = optparse.OptionParser()
    parser.add_option('-s', '--state_file', action='store',
                      dest='state_file',
                      default=os.path.expanduser('~/.kindle-utils.state'),
                      help='Path to file to load/store state from')
    parser.add_option('-b', '--book_dir', action='store',
                      dest='book_dir',
                      default='/media/Kindle/documents',
                      help='Path to Kindle userstore documents directory')
    parser.add_option('-B', '--book', action='store',
                      dest='book',
                      default=None,
                      help='ASIN of specific book to view')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
                      help='enable verbose logging')

    return parser.parse_args(args)


def main():
    # everything in UTC please!
    os.environ['TZ'] = 'UTC'
    time.tzset()

    logging.basicConfig()
    options, args = ParseOptions(sys.argv)
    if len(args) < 2:
        logging.fatal('You must specify a directory to read from!')
        sys.exit(1)
    log_parser.SetVerbosity(options.verbose)
    logs = log_parser.LoadHistory(options.state_file)
    if not logs:
        logs = log_parser.KindleLogs()
    logs.ProcessDirectory(args[1])
    log_parser.StoreHistory(logs, options.state_file)
    books = logs.books

    PrintBooks(books, options.book_dir, options.book, options.verbose)


if __name__ == '__main__':
    main()
