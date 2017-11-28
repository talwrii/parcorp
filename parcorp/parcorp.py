import argparse
import itertools
import logging
import os
import sqlite3

LOGGER = logging.getLogger()


PARSER = argparse.ArgumentParser(description='')

parsers = PARSER.add_subparsers(dest='command')

PARSER.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')

search_parser = parsers.add_parser('search', help='Search the datbase')
search_parser.add_argument('term', type=str, nargs='*', help='Search strings (SQLITE full text search)')
search_parser.add_argument('--skip', type=int, metavar='SKIP', help='Output one out of SKIP results')
search_parser.add_argument('--or', '-o', type=str, help='Search for any of these strings', action='append', dest='additional_terms')
search_parser.add_argument('--exact', '-x', action='store_true',
    default=False, help='search for exact string')
search_parser.add_argument('--count', '-c', action='store_true',
    default=False, help='Output the number of results')
search_parser.add_argument(
    '--words', '-w', type=int,
    help='Return searches with this many words')


language = search_parser.add_mutually_exclusive_group()

language.add_argument('--source', action='store_true', default=False, help='Only search source language')
language.add_argument('--target', action='store_true', default=False, help='Only search target')


load_parser = parsers.add_parser('load', help='Create database')
load_parser.add_argument('en', type=str)
load_parser.add_argument('de', type=str)
load_parser.add_argument('--limit', '-n', type=int, help='Only insert this many values')


filename = os.path.join(os.environ['HOME'], '.parcorp/data.sql')

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.command == 'load':
        with open(args.en) as english_stream:
            with open(args.de) as german_stream:
                os.unlink(filename)
                connection = sqlite3.connect(filename)
                connection.execute('create virtual table translation using fts3(english text, german text)')

                for index, (english, german) in enumerate(zip(english_stream, german_stream)):
                    if args.limit is not None and index > args.limit:
                        break

                    if index % 1000 == 0:
                        print index

                    connection.execute('insert into translation(english, german) values (?, ?)', (english.decode('utf8'), german.decode('utf8')))

                connection.commit()
    elif args.command == 'search':
        args.additional_terms = args.additional_terms or []
        connection = sqlite3.connect(filename)
        cursor = connection.cursor()
        term = ' '.join(args.term)
        if args.exact:
            term = '"{}"'.format(term)

        if args.target or args.source:
            language_field = 'german' if args.target else 'english'
            condition = ' or '.join(['{} MATCH ?'.format(language_field)] * (1 + len(args.additional_terms or [])))
            terms = (term.decode('utf8'), ) + tuple(x.decode('utf8') for x in args.additional_terms)
        else:
            condition = ' or '.join(['german MATCH ? or english MATCH ?'] * (1 + len(args.additional_terms or [])))
            terms = (term.decode('utf8'), term.decode('utf8')) + tuple(itertools.chain.from_iterable((x.decode('utf8'), x.decode('utf8')) for x in args.additional_terms))

        sql = 'select german, english from translation where {} order by length(german)'.format(condition)
        LOGGER.debug('Running sql %r'.format(sql))

        cursor.execute(sql, terms)
        if args.count:
            print len(cursor.fetchall())

        else:
            for index, (german, english) in enumerate(cursor.fetchall()):
                if args.skip is not None and index % args.skip != 0:
                    continue
                if args.words is not None:
                    if min(len(german.split(' ')), len(english.split(' '))) < args.words:
                        continue
                    
                print 'GERMAN', german,
                print 'ENGLISH', english,
                print
