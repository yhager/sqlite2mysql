#!/usr/bin/env python3

__author__ = "Klemen Tušar, Yuval Hager"
__email__ = "techouse@gmail.com, yhager@yhager.com"
__copyright__ = "GPL"
__version__ = "1.0.2"
__date__ = "2017-02-09"
__status__ = "Production"

import os.path, sqlite3, mysql.connector
from mysql.connector import errorcode


class SQLite3toMySQL:
    """
    Use this class to transfer an SQLite 3 database to MySQL.

    NOTE: Requires MySQL Connector/Python 2.0.4 or higher (https://dev.mysql.com/downloads/connector/python/)
    """
    def __init__(self, **kwargs):
        self._properties = kwargs
        self._sqlite_file = self._properties.get('sqlite_file', None)
        if not os.path.isfile(self._sqlite_file):
            print('SQLite file does not exist!')
            exit(1)
        self._mysql_user = self._properties.get('mysql_user', None)
        if self._mysql_user is None:
            print('Please provide a MySQL user!')
            exit(1)
        self._mysql_password = self._properties.get('mysql_password', None)
        if self._mysql_password is None:
            print('Please provide a MySQL password')
            exit(1)
        self._mysql_database = self._properties.get('mysql_database', 'transfer')
        self._mysql_host = self._properties.get('mysql_host', 'localhost')
        self._mysql_port = self._properties.get('mysql_port', 3306)

        self._mysql_integer_type = self._properties.get('mysql_integer_type', 'int(11)')
        self._mysql_string_type = self._properties.get('mysql_string_type', 'varchar(255)')

        self._sqlite = sqlite3.connect(self._sqlite_file)
        self._sqlite.row_factory = sqlite3.Row
        self._sqlite_cur = self._sqlite.cursor()

        self._mysql = mysql.connector.connect(
            user=self._mysql_user,
            password=self._mysql_password,
            host=self._mysql_host, port=self._mysql_port
        )
        self._mysql_cur = self._mysql.cursor(prepared=True)
        try:
            self._mysql.database = self._mysql_database
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_BAD_DB_ERROR:
                self._create_database()
            else:
                print(err)
                exit(1)

    def _create_database(self):
        try:
            self._mysql_cur.execute("CREATE DATABASE IF NOT EXISTS `{}` DEFAULT CHARACTER SET 'utf8'".format(self._mysql_database))
            self._mysql_cur.close()
            self._mysql.commit()
            self._mysql.database = self._mysql_database
            self._mysql_cur = self._mysql.cursor(prepared=True)
        except mysql.connector.Error as err:
            print('_create_database failed creating databse {}: {}'.format(self._mysql_database, err))
            exit(1)

    def _type(self, sqlite_type):
        # https://www.sqlite.org/datatype3.html#determination_of_column_affinity
        t = sqlite_type.lower()
        if 'int' in t:
            # integer affinity
            ret = 'tinyint' if t == 'tinyint' else self._mysql_integer_type
        elif 'char' in t or 'clob' in t or 'text' in t:
            # text affinity
            ret = self._mysql_string_type if 'char' in t else 'text'
        elif 'blob' in t or t == '':
            # blob affinity
            ret = 'blob'
        elif 'real' in t or 'floa' in t or 'doub' in t:
            # real affinity
            ret = 'double'
        else:
            # numeric affinity
            ret = t
        return ret

    def _create_table(self, table_name):
        primary_key = ''
        sql = 'CREATE TABLE IF NOT EXISTS `{}` ( '.format(table_name)
        self._sqlite_cur.execute('PRAGMA table_info("{}")'.format(table_name))
        sqls = list()
        for row in self._sqlite_cur.fetchall():
            column = dict(row)
            sqls.append(' `{name}` {type} {notnull} {auto_increment} '.format(
                name=column['name'],
                type=self._type(column['type']),
                notnull='NOT NULL' if column['notnull'] else 'NULL',
                auto_increment='AUTO_INCREMENT' if column['pk'] else ''
            ))
            if column['pk']:
                primary_key = column['name']
                sqls.append(' PRIMARY KEY (`{}`) '.format(primary_key))
        sql += ','.join(sqls)
        sql += ' ) ENGINE = InnoDB CHARACTER SET utf8'
        try:
            self._mysql_cur.execute(sql)
            self._mysql.commit()
        except mysql.connector.Error as err:
            print('_create_table failed creating table {}: {}'.format(table_name, err))
            print('tried: {}'.format(sql))
            exit(1)

    def transfer(self):
        self._sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        for row in self._sqlite_cur.fetchall():
            table = dict(row)
            # create the table
            self._create_table(table['name'])
            # populate it
            print('Transferring table {}'.format(table['name']))
            self._sqlite_cur.execute('SELECT * FROM "{}"'.format(table['name']))
            columns = [column[0] for column in self._sqlite_cur.description]
            try:
                self._mysql_cur.executemany("INSERT IGNORE INTO `{table}` ({fields}) VALUES ({placeholders})".format(
                    table=table['name'],
                    fields=('`{}`, ' * len(columns)).rstrip(' ,').format(*columns),
                    placeholders=('%s, ' * len(columns)).rstrip(' ,')
                ), (tuple(data) for data in self._sqlite_cur.fetchall()))
                self._mysql.commit()
            except mysql.connector.Error as err:
                print('_insert_table_data failed inserting data into table {}: {}'.format(table['name'], err))
                exit(1)
        print('Done!')


def main():
    """ For use in standalone terminal form """
    import sys, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--sqlite-file', dest='sqlite_file', default=None, help='SQLite3 db file')
    parser.add_argument('--mysql-user', dest='mysql_user', default=None, help='MySQL user')
    parser.add_argument('--mysql-password', dest='mysql_password', default=None, help='MySQL password')
    parser.add_argument('--mysql-database', dest='mysql_database', default=None, help='MySQL host')
    parser.add_argument('--mysql-host', dest='mysql_host', default='localhost', help='MySQL host')
    parser.add_argument('--mysql-port', dest='mysql_port', default=3306, help='MySQL port')
    parser.add_argument('--mysql-integer-type', dest='mysql_integer_type', default='int(11)', help='MySQL default integer field type')
    parser.add_argument('--mysql-string-type', dest='mysql_string_type', default='varchar(255)', help='MySQL default string field type')
    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        exit(1)

    converter = SQLite3toMySQL(
        sqlite_file=args.sqlite_file,
        mysql_user=args.mysql_user,
        mysql_password=args.mysql_password,
        mysql_database=args.mysql_database,
        mysql_host=args.mysql_host,
        mysql_port=args.mysql_port,
        mysql_integer_type=args.mysql_integer_type,
        mysql_string_type=args.mysql_string_type
    )
    converter.transfer()

if __name__ == '__main__':
    main()
