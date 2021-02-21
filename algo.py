from datetime import timedelta
from QuantConnect.Data.Custom.CBOE import *

class OptionChainProviderPutProtection(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2021, 1, 1)
        self.SetEndDate(2021, 2, 5)
        self.SetCash(10000000)
        self.equity = self.AddEquity("SPY", Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        self.vix = self.AddData(CBOE, "VIX").Symbol
        self.rank = 0
        self.contract = str()
        self.contractsAdded = set()
        
        # parameters ------------------------------------------------------------
        self.DTE = 20 # target days till expiration
        self.OTM = 0.01 # target percentage OTM of put
        self.IVlvl = 0.5 # enter position at this lvl of IV indicator
        # ------------------------------------------------------------------------
    
        # schedule Plotting function
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
        # schedule VIXRank function
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.VIXRank)
        self.SetWarmUp(timedelta(50)) 

    def VIXRank(self):
        history = self.History(CBOE, self.vix, 50, Resolution.Daily)
        # (Current - Min) / (Max - Min)
        self.rank = ((self.Securities[self.vix].Price - min(history["low"])) / (max(history["high"]) - min(history["low"])))
 
    def OnData(self, data):
        if(self.IsWarmingUp):
            return
        
        if not self.Portfolio[self.symbol].Invested:
            self.SetHoldings(self.symbol, 0.95)
        
        if self.rank > self.IVlvl:
            self.BuyPut(data)
        
        if self.contract:
            if (self.contract.ID.Date - self.Time) <= timedelta(2):
                self.Liquidate(self.contract)
                self.Log("Closed: too close to expiration")
                self.contract = str()

    def BuyPut(self, data):
        if self.contract == str():
            self.contract = self.OptionsFilter(data)
            return
        
        elif not self.Portfolio[self.contract].Invested and data.ContainsKey(self.contract):
            self.Buy(self.contract, round(self.Portfolio[self.symbol].Quantity / 100))

    def OptionsFilter(self, data):

        contracts = self.OptionChainProvider.GetOptionContractList(self.symbol, data.Time)
        self.underlyingPrice = self.Securities[self.symbol].Price
        otm_puts = [i for i in contracts if i.ID.OptionRight == OptionRight.Put and
                                            self.underlyingPrice - i.ID.StrikePrice > self.OTM * self.underlyingPrice and
                                            self.DTE - 8 < (i.ID.Date - data.Time).days < self.DTE + 8]
        if len(otm_puts) > 0:
            contract = sorted(sorted(otm_puts, key = lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                     key = lambda x: self.underlyingPrice - x.ID.StrikePrice)[0]
            if contract not in self.contractsAdded:
                self.contractsAdded.add(contract)
                self.AddOptionContract(contract, Resolution.Minute)
            return contract
        else:
            return str()

    def Plotting(self):
        self.Plot("Vol Chart", "Rank", self.rank)
        self.Plot("Vol Chart", "lvl", self.IVlvl)
        self.Plot("Data Chart", self.symbol, self.Securities[self.symbol].Close)
        
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type==SecurityType.Option]
        if option_invested:
                self.Plot("Data Chart", "strike", option_invested[0].ID.StrikePrice)
                
        self.MarketOnOpenOrder("SPY", 1) #Buy one share of the spy every day, this means we're trading enough for the sake of competition

    def OnOrderEvent(self, orderEvent):
        # log order events
        self.Log(str(orderEvent))
