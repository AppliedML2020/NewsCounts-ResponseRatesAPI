import os
import logging
import sqlalchemy
import config
import pymysql
import datetime
from datetime import date

from flask import Flask, render_template, jsonify, abort, request, make_response
from flask.json import JSONEncoder


class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, date):
                return obj.isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)

app = Flask(__name__)
app.json_encoder = CustomJSONEncoder

logger = logging.getLogger()

db = sqlalchemy.create_engine(
    # Equivalent URL:
    # mysql+pymysql://<db_user>:<db_pass>@/<db_name>?unix_socket=/cloudsql/<cloud_sql_instance_name>
    sqlalchemy.engine.url.URL(
        drivername="mysql+pymysql",
        username=config.config_vars['db_user'],
        password=config.config_vars['db_pass'],
        database=config.config_vars['db_name'],
        query={"unix_socket": "/cloudsql/{}".format(config.config_vars['cloud_sql_connection_name'])},
    ),
    # ... Specify additional properties here.
    # [START_EXCLUDE]
    # [START cloud_sql_mysql_sqlalchemy_limit]
    # Pool size is the maximum number of permanent connections to keep.
    pool_size=5,
    # Temporarily exceeds the set pool_size if no connections are available.
    max_overflow=2,
    # The total number of concurrent connections for your application will be
    # a total of pool_size and max_overflow.
    # [END cloud_sql_mysql_sqlalchemy_limit]
    # [START cloud_sql_mysql_sqlalchemy_backoff]
    # SQLAlchemy automatically uses delays between failed connection attempts,
    # but provides no arguments for configuration.
    # [END cloud_sql_mysql_sqlalchemy_backoff]
    # [START cloud_sql_mysql_sqlalchemy_timeout]
    # 'pool_timeout' is the maximum number of seconds to wait when retrieving a
    # new connection from the pool. After the specified amount of time, an
    # exception will be thrown.
    pool_timeout=30,  # 30 seconds
    # [END cloud_sql_mysql_sqlalchemy_timeout]
    # [START cloud_sql_mysql_sqlalchemy_lifetime]
    # 'pool_recycle' is the maximum number of seconds a connection can persist.
    # Connections that live longer than the specified amount of time will be
    # reestablished
    pool_recycle=1800,  # 30 minutes
    # [END cloud_sql_mysql_sqlalchemy_lifetime]
    # [END_EXCLUDE]
)

available_data = ["CRRALL","CRRINT","DAVG","DINTAVG","DRRALL","DRRINT"]

available_data_tract = ["CRRALL","CRRINT","DRRALL","DRRINT"]

@app.route("/")
def home():
    return  render_template("home.html")

@app.route('/api/response_rates/state', methods=['GET'])
def get_state_data():
    if not valid_state_request():
        abort(400,state_request_msg())

    try: 
        with db.connect() as conn:
            date_interval = get_date_interval()
            where_state = get_where_state()
            selection = get_selection("state")

            query = conn.execute(
                f"SELECT {selection} FROM state_response_rates WHERE NOT ISNULL(RESP_DATE) {date_interval} {where_state} ORDER BY RESP_DATE DESC, state_short;"
            ).fetchall()
            return jsonify([dict(row) for row in query])
    except Exception as e:
        logger.exception(e)
        abort(400)

@app.route('/api/response_rates/county', methods=['GET'])
def get_county_data():
    if not valid_county_request():
        abort(400,county_request_msg())

    try: 
        with db.connect() as conn:
            date_interval = get_date_interval()
            where_state = get_where_state()
            where_county = get_where_county()
            selection = get_selection("county")
            
            query = conn.execute(
                f"SELECT {selection} FROM county_response_rates WHERE NOT ISNULL(RESP_DATE) {date_interval} {where_state} {where_county} ORDER BY RESP_DATE DESC, state_short, county_name;"
            ).fetchall()
            return jsonify([dict(row) for row in query])
    except Exception as e:
        logger.exception(e)
        abort(400)

@app.route('/api/response_rates/tract', methods=['GET'])
def get_tract_data():
    if not valid_tract_request():
        abort(400,tract_request_msg())

    try: 
        with db.connect() as conn:
            date_interval = get_date_interval()
            where_state = get_where_state()
            where_county = get_where_county()
            where_tract = get_where_tract()
            selection = get_selection("tract")
            
            query = conn.execute(
                f"SELECT {selection} FROM tract_response_rates WHERE NOT ISNULL(RESP_DATE) {date_interval} {where_state} {where_county} {where_tract} ORDER BY RESP_DATE DESC, state_short, county_name, tract;"
            ).fetchall()
            return jsonify([dict(row) for row in query])
    except Exception as e:
        logger.exception(e)
        abort(400)
        
    
if __name__ == "__main__":
    app.run(debug=True)

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

@app.errorhandler(400)
def some_error(error):
    return make_response(jsonify({'error': str(error)}), 400)

def valid_state_request():
    return valid_dates() and valid_data("state") and valid_state()

def valid_county_request():
    return valid_dates() and valid_data("county") and valid_state("COUNTY" in request.args) and valid_county()

def valid_tract_request():
    return valid_dates() and valid_data("tract") and valid_state(True) and valid_county("TRACT" in request.args) and valid_tract()

def state_request_msg():
    msg = "Something went wrong"
    if not valid_dates():
        return "Invalid dates format"
    if not valid_data("state"):
        return "Invalid DATA value"
    if not valid_state():
        return "Invalid STATE value"
    return msg

def county_request_msg():
    msg = "Something went wrong"
    if not valid_dates():
        return "Invalid dates format"
    if not valid_data("county"):
        return "Invalid data value"
    if not valid_state("COUNTY" in request.args):
        return "Invalid STATE value"
    if not valid_county():
        return "Invalid COUNTY value"
    return msg

def tract_request_msg():
    msg = "Something went wrong"
    if not valid_dates():
        return "Invalid dates format"
    if not valid_data("tract"):
        return "Invalid data value"
    if not valid_state(True):
        return "Invalid STATE value"
    if not valid_county("TRACT" in request.args):
        return "Invalid COUNTY value"
    if not valid_tract():
        return "Invalid TRACT value"
    return msg

def valid_state(required=False):
    if not required and "STATE" not in request.args:
        return True
    else:
        if "STATE" not in request.args:
            return False
        state = request.args["STATE"]
        try: 
            with db.connect() as conn:
                query = conn.execute(
                    f"SELECT DISTINCT state_short FROM state_response_rates ;"
                ).fetchall()
                return state in [row[0] for row in query]
        except Exception as e:
            logger.exception(e)
            return False

def valid_county(required=False):
    if not required and "COUNTY" not in request.args:
        return True
    else:
        if "COUNTY" not in request.args:
            return False
        county = int(request.args["COUNTY"])
        state = request.args["STATE"]
        try: 
            with db.connect() as conn:
                query = conn.execute(
                    f"SELECT DISTINCT CONVERT(county,SIGNED INTEGER) FROM county_response_rates WHERE state_short=\"{state}\" ;"
                ).fetchall()
                return county in [int(row[0]) for row in query]
        except Exception as e:
            logger.exception(e)
            return False

def valid_tract(required=False):
    if not required and "TRACT" not in request.args:
        return True
    else:
        if "TRACT" not in request.args:
            return False
        tract = int(request.args["TRACT"])
        state = request.args["STATE"]
        county = int(request.args["COUNTY"])
        try: 
            with db.connect() as conn:
                query = conn.execute(
                    f"SELECT DISTINCT CONVERT(tract,SIGNED  INTEGER) FROM tract_response_rates  WHERE state_short=\"{state}\" AND CONVERT(county,SIGNED  INTEGER)={county} ;"
                ).fetchall()
                return tract in [int(row[0]) for row in query]
        except Exception as e:
            logger.exception(e)
            return False


def valid_data(type):
    a_d = available_data
    if type=="tract":
        a_d = available_data_tract
    if "DATA" in request.args:
        return sum([ x not in a_d for x in request.args["DATA"].split(",") ]) == 0
    else:
        return True

def valid_dates():
    if "FROM" not in request.args and "TO" not in request.args:
        return True
    valid = False
    if "FROM" in request.args and "TO" in request.args:
        date_from = request.args['FROM']
        date_to = request.args['TO']
        valid= is_date(date_from) and is_date(date_to)
    return valid

def is_date(d):
    isValid= True
    year,month,day = d.split("-")
    try:
        datetime.datetime(int(year),int(month),int(day))
    except:
        isValid= False

    return isValid

def get_date_interval():
    if "FROM" in request.args and "TO" in request.args:
        date_from = request.args['FROM']
        date_to = request.args['TO']
        return f" AND (RESP_DATE BETWEEN \"{date_from}\" AND \"{date_to}\") "

    return ""

def get_where_state():
    if "STATE" in request.args:
        state = request.args["STATE"]
        return f" AND state_short = \"{state}\" "
    return ""

def get_where_county():
    if "COUNTY" in request.args:
        county = int(request.args["COUNTY"])
        return f" AND CONVERT(county,SIGNED  INTEGER) = {county} "
    return ""

def get_where_tract():
    if "TRACT" in request.args:
        tract = int(request.args["TRACT"])
        return f" AND CONVERT(tract,SIGNED  INTEGER) = {tract} "
    return ""

def get_selection(type):
    a_d = available_data
    if type=="tract":
        a_d = available_data_tract

    if "DATA" not in request.args:
        data = ", ".join(a_d)
    else:
        data = request.args["DATA"]
    if type=="state":
        return f" RESP_DATE, GEO_ID, {data}, state, state_name, state_short "
    if type=="county":
        return f" RESP_DATE, GEO_ID, {data}, state, state_name, state_short, county, county_name "
    if type=="tract":
        return f" RESP_DATE, GEO_ID, {data}, state, state_name, state_short, county, county_name, tract "
    return "*"
