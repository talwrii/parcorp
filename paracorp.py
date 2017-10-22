import argparse
import sqlite3
import os

PARSER = argparse.ArgumentParser(description='')

parsers = PARSER.add_subparsers(dest='command')

search_parser = parsers.add_parser('search', help='Search the datbase')
search_parser.add_argument('term', type=str, nargs='*')

load_parser = parsers.add_parser('load', help='Create database')
load_parser.add_argument('en', type=str)
load_parser.add_argument('de', type=str)
load_parser.add_argument('--limit', '-n', type=int, help='Only insert this many values')

args = PARSER.parse_args()

filename = "data/data.sql"

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
    connection = sqlite3.connect(filename)
    cursor = connection.cursor()
    term = ' '.join(args.term)
    cursor.execute('select german, english from translation where german MATCH ? or english MATCH ? order by length(german)', (term.decode('utf8'), term.decode('utf8')))
    for german, english in cursor.fetchall():
        print 'GERMAN', german,
        print 'ENGLISH', english,
        print
