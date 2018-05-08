# coding=utf-8

import sqlite3
import os.path as op
from future.utils import iteritems

DATABASE = op.join(op.dirname(op.abspath(__file__)), 'database/tradebot.db')

try:
    connection = sqlite3.connect(DATABASE, check_same_thread = False)
except Exception as e:
    raise e

class Database(object):

    def __init__(self):
        self.cursor = connection.cursor()

    def trader_exists(self, thread_name, key):
        sql = "select id from trader_data where thread_name=? and key=?"
        self.cursor.execute(sql, (thread_name, key))
        data = self.cursor.fetchone()
        if not data:
            return False
        return True

    def trader_update(self, data):
        """
        data = {'thread_name': name, 'pairs': {'key': 'value', 'key': 'value'}}
        """
        thread_name = data['thread_name']
        inserts = []
        updates = []
        for (key, val) in iteritems(data['pairs']):
            if self.trader_exists(thread_name, key):
                updates.append((val, thread_name, key))
            else:
                inserts.append((thread_name, key, val))

        if inserts:
            self.cursor.executemany("insert into trader_data (thread_name, key, value) values (?,?,?)", inserts)

        if updates:
            self.cursor.executemany("update trader_data set value=? where thread_name=? and key=?", updates)
        connection.commit()

    def trader_read(self, thread_name, key=''):
        data = {'thread_name': thread_name, 'pairs': {}}
        if not key:
            self.cursor.execute("select key, value from trader_data where thread_name='thread-1'")
            rows = self.cursor.fetchall()
            for row in rows:
                data['pairs'][row[0]]= row[1]
        else:
            self.cursor.execute("select value from trader_data where thread_name=? and key=?", (thread_name, key))
            row = self.cursor.fetchone()
            if row:
                data['pairs'][key] = row[0]
        return data

    def order_exists(self, order_id):
        sql = "select id from order_data where order_id=?"
        self.cursor.execute(sql, (str(order_id),))
        if not self.cursor.fetchone():
            return False
        return True

    def order_update(self, data):
        tup = (data['price'], data['orig_quantity'], data['executed_quantity'], data['side'], int(data['time']), data['status'], str(data['order_id']))
        if self.order_exists(data['order_id']):
            sql = "update order_data set price=?, orig_qty=?, exec_qty=?, side=?, time=?, status=? where order_id=?"
        else:
            sql = "insert into order_data (price, orig_qty, exec_qty, side, time, status, order_id) values (?,?,?,?,?,?,?)"
        self.cursor.execute(sql, tup)
        connection.commit()

    def order_read(self, order_id, key=''):
        if not key:
            sql = "select price, orig_qty, exec_qty, side, time, status from order_data where order_id=?"
            self.cursor.execute(sql, (str(order_id),))
            order = self.cursor.fetchone()
            if not order:
                return None
            order_dict = {'order_id': str(order_id), 'price': order[0], 'orig_quantity': order[1], 'executed_quantity': order[2], 'side': order[3], 'time': order[4], 'status': order[5]}
        else:
            sql = "select %s from order_data where order_id=?" % key
            self.cursor.execute(sql, (str(order_id),))
            order = self.cursor.fetchone()
            if not order:
                return None
            order_dict = {'order_id': str(order_id), key: order[0]}
        return order_dict
