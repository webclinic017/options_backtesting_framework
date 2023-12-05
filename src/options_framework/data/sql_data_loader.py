import dataclasses
import datetime

import pandas as pd
from pandas import DataFrame, Series
import pyodbc

from options_framework.config import settings
from options_framework.data.data_loader import DataLoader
from options_framework.option import Option
from options_framework.option_types import OptionType, SelectFilter

class SQLServerDataLoader(DataLoader):

    def __init__(self, start: datetime.datetime, end: datetime.datetime, select_filter: SelectFilter,
                 fields_list: list[str], *args, **kwargs):
        super().__init__(start, end, select_filter, fields_list, *args, **kwargs)
        server = settings.SERVER
        database = settings.DATABASE
        username = settings.USERNAME
        password = settings.PASSWORD
        self.connection_string = 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=' + server + ';DATABASE=' + database \
                                 + ';UID=' + username + ';PWD=' + password
        self.last_loaded_date = start
        self.start_load_date = start
        self.datetimes_list = self._get_datetimes_list()

    def load_cache(self, start: datetime.datetime):
        self.start_load_date = start
        start_loc = self.datetimes_list.index.get_loc(str(start))
        end_loc = start_loc + 10_000
        end_loc = end_loc if end_loc < len(self.datetimes_list) else len(self.datetimes_list)-1
        query_end_date = self.datetimes_list.iloc[end_loc].name.to_pydatetime()
        query = self._build_query(start, query_end_date)

        connection = pyodbc.connect(self.connection_string)
        df = pd.read_sql(query, connection, index_col="quote_datetime", parse_dates=True)
        df.index = pd.to_datetime(df.index)
        self.data_cache = df
        connection.close()
        self.last_loaded_date = query_end_date # set to end of data loaded

    def get_next_option_chain(self, quote_datetime):

        df = self.data_cache.loc[str(quote_datetime)]

        options = [Option(
            option_id=row['option_id'],
            symbol=row['symbol'],
            expiration=row['expiration'].date(),
            strike=row['strike'],
            option_type=OptionType.CALL if row['option_type'] == 1 else OptionType.PUT,
            quote_datetime=i if 'quote_datetime' in self.fields_list else None,
            spot_price=row['spot_price'] if 'spot_price' in self.fields_list else None,
            bid=row['bid'] if 'bid' in self.fields_list else None,
            ask=row['ask'] if 'ask' in self.fields_list else None,
            price=row['price'] if 'price' in self.fields_list else None,
            delta=row['delta'] if 'delta' in self.fields_list else None,
            gamma=row['gamma'] if 'gamma' in self.fields_list else None,
            theta=row['theta'] if 'theta' in self.fields_list else None,
            vega=row['vega'] if 'vega' in self.fields_list else None,
            rho=row['rho'] if 'rho' in self.fields_list else None,
            open_interest=row['open_interest'] if 'open_interest' in self.fields_list else None,
            implied_volatility=row['implied_volatility'] if 'implied_volatility' in self.fields_list else None
            ) for i, row in df.iterrows()]

        super().on_option_chain_loaded_loaded(quote_datetime=quote_datetime, option_chain=options)

    def _build_query(self, start_date: datetime.datetime, end_date: datetime.datetime):
        fields = ['option_id'] + self.fields_list
        field_mapping = ','.join([db_field for option_field, db_field in settings.FIELD_MAPPING.items() \
                                  if option_field in fields])
        filter_dict = dataclasses.asdict(self.select_filter)
        query = settings.SELECT_OPTIONS_QUERY['select']
        query += field_mapping
        query += settings.SELECT_OPTIONS_QUERY['from']
        query += (settings.SELECT_OPTIONS_QUERY['where']
                  .replace('{symbol}', self.select_filter.symbol)
                  .replace('{start_date}', str(start_date))
                  .replace('{end_date}', str(end_date)))
        if self.select_filter.option_type:
            query += f' and option_type = {self.select_filter.option_type.value}'

        for fltr in [f for f in filter_dict.keys() if 'range' in f]:
            name, low_val, high_val = fltr[:-6], filter_dict[fltr]['low'], filter_dict[fltr]['high']
            for val in [low_val, high_val]:
                if val is not None:# and high_val is not None:
                    operator = ">=" if val is low_val else "<="
                    if name == 'expiration':
                        query += f' and {name} {operator} CONVERT(datetime2, \'{val}\')' # and CONVERT(datetime2, \'{high_val}\')'
                    else:
                        query += f' and {name} {operator} {val}'

        query += ' order by \'quote_datetime\', \'expiration\', \'strike\''

        return query

    def _get_datetimes_list(self):
        symbol = self.select_filter.symbol
        start_date = self.start_datetime
        end_date = self.end_datetime
        #quote_field = [f[1] for f in settings.FIELD_MAPPING.items() if f[0] == 'quote_datetime'][0]
        query = settings.SELECT_OPTIONS_QUERY.quote_datetime_list_query.replace('{symbol}', symbol).replace('{start_date}', str(start_date)).replace('{end_date}', str(end_date))
        #.replace('{start_date}', str(self.start_load_date)).replace('{end_date}', str(self.end_datetime)))

            #f'select distinct {settings.SELECT_OPTIONS_QUERY.quote_datetime_field} {settings.SELECT_OPTIONS_QUERY["from"]} where symbol=\'{self.select_filter.symbol}\' order by {settings.SELECT_OPTIONS_QUERY.quote_datetime_field}'
        connection = pyodbc.connect(self.connection_string)
        df = pd.read_sql(query, connection, parse_dates=True, index_col=[settings.SELECT_OPTIONS_QUERY.quote_datetime_field])
        df.index = pd.to_datetime(df.index)
        connection.close()
        return df
