#!/usr/bin/env python3
"""Cyberjunky's 3Commas bot helpers."""
import argparse
import configparser
import json
import os
import time
import sys
from pathlib import Path

from helpers.logging import Logger, NotificationHandler
from helpers.misc import get_coinmarketcap_data, populate_pair_lists
from helpers.threecommas import (
    get_threecommas_account,
    get_threecommas_market,
    init_threecommas_api,
    load_blacklist,
    set_threecommas_bot_pairs,
)


def load_config():
    """Create default or load existing config file."""

    cfg = configparser.ConfigParser()
    if cfg.read(f"{datadir}/{program}.ini"):
        return cfg

    cfg["settings"] = {
        "timezone": "Europe/Amsterdam",
        "timeinterval": 86400,
        "debug": False,
        "logrotate": 7,
        "botids": [12345, 67890],
        "start-number": 1,
        "end-number": 200,
        "3c-apikey": "Your 3Commas API Key",
        "3c-apisecret": "Your 3Commas API Secret",
        "cmc-apikey": "Your CoinMarketCap API Key",
        "notifications": False,
        "notify-urls": ["notify-url1"],
    }

    with open(f"{datadir}/{program}.ini", "w") as cfgfile:
        cfg.write(cfgfile)

    return None


def upgrade_config(cfg):
    """Upgrade config file if needed."""

    try:
        cfg.get("settings", "start-number")
    except configparser.NoOptionError:
        logger.error(f"Upgrading config file '{datadir}/{program}.ini'")
        cfg.set("settings", "start-number", "1")
        cfg.set("settings", "end-number", cfg.get("settings", "numberofpairs"))
        cfg.remove_option("settings", "numberofpairs")

        with open(f"{datadir}/{program}.ini", "w+") as cfgfile:
            cfg.write(cfgfile)

    return cfg


def coinmarketcap_pairs(thebot):
    """Find new pairs and update the bot."""

    # Gather bot settings
    base = thebot["pairs"][0].split("_")[0]
    exchange = thebot["account_name"]

    logger.info("Bot base currency: %s" % base)

    # Start from scratch
    newpairs = list()
    badpairs = list()
    blackpairs = list()

    # Get marketcode (exchange) from account
    marketcode = get_threecommas_account(logger, api, thebot["account_id"])
    if not marketcode:
        return

    # Load tickerlist for this exchange
    tickerlist = get_threecommas_market(logger, api, marketcode)
    logger.info("Bot exchange: %s (%s)" % (exchange, marketcode))

    # Parse CoinMarketCap data
    for entry in coinmarketcap:
        try:
            coin = entry["symbol"]
            pair = base + "_" + coin

            # Populate lists
            populate_pair_lists(
                pair, blacklist, blackpairs, badpairs, newpairs, tickerlist
            )

        except KeyError as err:
            logger.error(
                "Something went wrong while parsing CoinMarketCap data. KeyError for field: %s"
                % err
            )
            return

    logger.debug("These pairs are blacklisted and were skipped: %s" % blackpairs)

    logger.debug(
        "These pairs are invalid on '%s' and were skipped: %s" % (marketcode, badpairs)
    )

    if not newpairs:
        logger.info(
            "None of the by CoinMarketCap suggested pairs have been found on the %s (%s) exchange!"
            % (exchange, marketcode)
        )
        return

    # Update the bot with the new pairs
    set_threecommas_bot_pairs(logger, api, thebot, newpairs)


# Start application
program = Path(__file__).stem

# Parse and interpret options.
parser = argparse.ArgumentParser(description="Cyberjunky's 3Commas bot helper.")
parser.add_argument(
    "-d", "--datadir", help="directory to use for config and logs files", type=str
)
parser.add_argument(
    "-b", "--blacklist", help="local blacklist to use instead of 3Commas's", type=str
)

args = parser.parse_args()
if args.datadir:
    datadir = args.datadir
else:
    datadir = os.getcwd()

# pylint: disable-msg=C0103
if args.blacklist:
    blacklistfile = args.blacklist
else:
    blacklistfile = None

# Create or load configuration file
config = load_config()
if not config:
    # Initialise temp logging
    logger = Logger(datadir, program, None, 7, False, False)
    logger.info(
        f"Created example config file '{datadir}/{program}.ini', edit it and restart the program"
    )
    sys.exit(0)
else:
    # Handle timezone
    if hasattr(time, "tzset"):
        os.environ["TZ"] = config.get(
            "settings", "timezone", fallback="Europe/Amsterdam"
        )
        time.tzset()

    # Init notification handler
    notification = NotificationHandler(
        program,
        config.getboolean("settings", "notifications"),
        config.get("settings", "notify-urls"),
    )

    # Initialise logging
    logger = Logger(
        datadir,
        program,
        notification,
        int(config.get("settings", "logrotate", fallback=7)),
        config.getboolean("settings", "debug"),
        config.getboolean("settings", "notifications"),
    )

    # Upgrade config file if needed
    config = upgrade_config(config)

    logger.info(f"Loaded configuration from '{datadir}/{program}.ini'")

# Initialize 3Commas API
api = init_threecommas_api(config)

# Lunacrush GalayScore or AltRank pairs
while True:

    # Reload config files and refetch data to catch changes
    config = load_config()
    logger.info(f"Reloaded configuration from '{datadir}/{program}.ini'")

    # Configuration settings
    botids = json.loads(config.get("settings", "botids"))
    timeint = int(config.get("settings", "timeinterval"))

    # Update the blacklist
    blacklist = load_blacklist(logger, api, blacklistfile)

    # Download CoinMarketCap data
    coinmarketcap = get_coinmarketcap_data(logger, config)

    # Walk through all bots configured
    for bot in botids:
        error, data = api.request(
            entity="bots",
            action="show",
            action_id=str(bot),
        )
        if data:
            coinmarketcap_pairs(data)
        else:
            if error and "msg" in error:
                logger.error("Error occurred updating bots: %s" % error["msg"])
            else:
                logger.error("Error occurred updating bots")

    if timeint > 0:
        localtime = time.time()
        nexttime = localtime + int(timeint)
        timeresult = time.strftime("%H:%M:%S", time.localtime(nexttime))
        logger.info("Next update in %s Seconds at %s" % (timeint, timeresult), True)
        time.sleep(timeint)
    else:
        break
