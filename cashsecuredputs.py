import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

ENV = "sandbox" #Use "sandbox" when testing, and "api" if you have an account at Tradier
API_TOKEN = "" #Fill in your Tradier API Token here


###
#Script starts here
###
def main():
    #Get list of symbols from file
    filename_in = "symbols.csv"
    listOfSymbols = importCSV(filename_in)

    #Find Cash Secured Puts
    #Parameters: Symbols, min DTE, max DTE
    findCashSecuredPuts(listOfSymbols, 10, 47)

###
#API Functions
###

#Get Data from Tradier API
def getAPIData(url):
    bearer_token = f"Bearer {API_TOKEN}"
    headers={'Authorization': bearer_token, 'Accept': 'application/json'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return json.loads(response.content.decode('utf-8'))

#Get all the upcoming expirations for given symbol
def getOptionExpirations(symbol):
    url = f"https://{ENV}.tradier.com/v1/markets/options/expirations?symbol={symbol}"
    expirations_data = getAPIData(url)
    expirations = []
    if (expirations_data['expirations']):
        expirations = expirations_data['expirations']['date']
    
    return expirations

#Retrieve the options chain for given symbol and expiration
def getOptionsChain(symbol, expiration):
    url = f"https://{ENV}.tradier.com/v1/markets/options/chains?symbol={symbol}&expiration={expiration}&greeks=true"
    options_chain_data = getAPIData(url)
    options_chain = []
    if (options_chain_data['options']):
        options_chain = options_chain_data['options']['option']
        
    return options_chain

#Retrieves latest stock price from Tradier Market API
def getLastStockPrice(symbol):
    url = f"https://{ENV}.tradier.com/v1/markets/quotes?symbols={symbol}"
    quote_data = getAPIData(url)
    last_price = -1
    if ('quote' in quote_data['quotes']):
        last_price = quote_data['quotes']['quote']['last']
    
    return last_price

###
#Utility functions
###

#Import CSV files using Pandas library
def importCSV(filename_in):
    data = pd.read_csv(filename_in)
    symbols = data['Symbol'].to_list()
    return symbols

#Limit expirations of symbol to provided min_dte (Min Days Until Expiration) and max_dte (Max Days Until Expiration)
def listOfLimitedExpirations(symbol, min_dte, max_dte):
    #Get option expirations for symbol
    expirations_list = getOptionExpirations(symbol)

    expirations = []

    if(isinstance(expirations_list, str)):
        return []

    for expiration_date in expirations_list:
        #Extract dates within set DTE
        date_object = datetime.strptime(expiration_date,"%Y-%m-%d")
        expiration_min_date = datetime.now() + timedelta(min_dte)
        expiration_max_date = datetime.now() + timedelta(max_dte)

        if (date_object <= expiration_min_date):
            continue

        if (date_object >= expiration_max_date):
            continue

        expirations.append(expiration_date)

    return expirations

def exportToFile(data, filename_out):
    output = pd.DataFrame(data, columns=['Symbol','Expiration','Strike','Bid','Ask','Volume','Delta','Premium'])

    output.to_csv(filename_out,index=False)

#Creates a new dictionary with options data
def gatherOptionData(option):
    option_data = {}

    option_data['symbol'] = option['underlying']
    option_data['type'] = option['option_type']
    option_data['expiration'] = option['expiration_date']
    option_data['strike'] = option['strike']
    option_data['bid'] = option['bid']
    option_data['ask'] = option['ask']
    option_data['volume'] = option['volume']
    option_data['open_int'] = option['open_interest']

    #Add necessary greeks here
    option_greeks = option.get('greeks',None)

    if (option_greeks):
        option_data['delta'] = option_greeks['delta']
        option_data['theta'] = option_greeks['theta']
        option_data['gamma'] = option_greeks['gamma']

    return option_data

###
# Main function for filtering the PUT options we are looking for
# You will have to set your own critera
# Generally, for minimum critera, you want:
# tight bid/ask spreads (under .15)
# Some liquidity (Looking for volume greater than 0)
# Certain delta, minium premium, etc.
###

def findCashSecuredPuts(ListOfSymbols, minDays, maxDays):

    #Adjust these according to your criteria
    MAX_BID_ASK_SPREAD = .15
    MIN_PRICE = 10
    MAX_PRICE = 70
    MIN_PREM = .30
    MAX_DELTA = -.2

    matching_options = []
    data_frame = []
    for symbol in ListOfSymbols:
        print(f"Processing {symbol}...")

        #Depending on your list of symbols, you may want to filter by current price, since you will need buying power
        last_price = getLastStockPrice(symbol)
        if (last_price <= MIN_PRICE or last_price >= MAX_PRICE):
            continue

        #We only want options expiring within a certain timeframe
        expirations_list = listOfLimitedExpirations(symbol, minDays, maxDays)

        numOptions = 0
        for expiration in expirations_list:

            #First we need the options chain
            options = getOptionsChain(symbol, expiration)

            for option_item in options:

                #This will just gather data from option into a more useful dictionary
                option = gatherOptionData(option_item)

                #Start filtering by your criteria here

                #Make sure there is a bid/ask, otherwise there's probably no liquidity
                if (option['bid'] is None or option['ask'] is None):
                    continue

                #Estimated premium (this goes by the approx mid price)
                premium = round((option['bid'] + option['ask']) / 2,2)

                #Check for delta if it exists
                delta = -999
                if ('delta' in option):
                    delta = option['delta']

                #Filter out the options we actually want
                if (option['type'] == "put"
                    and option['bid'] > 0
                    and delta >= MAX_DELTA
                    and premium >= MIN_PREM
                    and (option['ask'] - option['bid']) <= MAX_BID_ASK_SPREAD
                    and option['volume'] > 0
                ):

                    #Format the output
                    option_output = '{}, {}, BID:{}, ASK:{}, {}, {}(D), Premium: {}'\
                        .format(
                            option['expiration'],
                            option['strike'],
                            option['bid'],
                            option['ask'],
                            option['volume'],
                            delta,
                            premium)

                    #Separate by symbol
                    if (numOptions == 0):
                        matching_options.append(f"Symbol: {symbol}")
                        numOptions += 1

                    #Print the screen when a match is found
                    print(f"Wheel: {option_output}")

                    #Add data to Pandas DataFrame
                    data_frame.append([symbol,
                                        option['expiration'],
                                        option['strike'],
                                        option['bid'],
                                        option['ask'],
                                        option['volume'],
                                        delta,
                                        premium])

    #Export results to a new csv file
    exportToFile(data_frame, "output_cash_secured_puts.csv")

if __name__ == '__main__':
    main()
