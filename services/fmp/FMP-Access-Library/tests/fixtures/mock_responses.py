"""Mock API response data for testing."""

from typing import Any

# Mock Quote Response
MOCK_QUOTE_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 185.50,
        "changePercentage": 1.25,
        "change": 2.30,
        "dayLow": 183.00,
        "dayHigh": 186.20,
        "yearHigh": 199.62,
        "yearLow": 124.17,
        "marketCap": 2850000000000,
        "priceAvg50": 180.25,
        "priceAvg200": 175.50,
        "exchange": "NASDAQ",
        "volume": 55000000,
        "avgVolume": 50000000,
        "open": 184.00,
        "previousClose": 183.20,
        "eps": 6.15,
        "pe": 30.16,
        "earningsAnnouncement": "2024-02-01T16:30:00.000+0000",
        "sharesOutstanding": 15370000000,
        "timestamp": 1705951200,
    }
]

# Mock Company Profile Response
MOCK_PROFILE_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "price": 185.50,
        "beta": 1.29,
        "averageVolume": 50000000,
        "marketCap": 2850000000000,
        "lastDividend": 0.96,
        "range": "124.17-199.62",
        "changes": 2.30,
        "companyName": "Apple Inc.",
        "currency": "USD",
        "cik": "0000320193",
        "isin": "US0378331005",
        "cusip": "037833100",
        "exchange": "NASDAQ",
        "industry": "Consumer Electronics",
        "website": "https://www.apple.com",
        "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.",
        "ceo": "Timothy Cook",
        "sector": "Technology",
        "country": "US",
        "fullTimeEmployees": "164000",
        "phone": "14089961010",
        "address": "One Apple Park Way",
        "city": "Cupertino",
        "state": "CA",
        "zip": "95014",
        "dcfDiff": 15.50,
        "dcf": 170.00,
        "image": "https://financialmodelingprep.com/image-stock/AAPL.png",
        "ipoDate": "1980-12-12",
        "defaultImage": False,
        "isEtf": False,
        "isActivelyTrading": True,
        "isAdr": False,
        "isFund": False,
    }
]

# Mock Income Statement Response
MOCK_INCOME_STATEMENT_RESPONSE: list[dict[str, Any]] = [
    {
        "date": "2023-09-30",
        "symbol": "AAPL",
        "reportedCurrency": "USD",
        "cik": "0000320193",
        "filingDate": "2023-11-03",
        "acceptedDate": "2023-11-02 18:01:13",
        "fiscalYear": "2023",
        "period": "FY",
        "revenue": 383285000000,
        "costOfRevenue": 214137000000,
        "grossProfit": 169148000000,
        "grossProfitRatio": 0.4413,
        "researchAndDevelopmentExpenses": 29915000000,
        "generalAndAdministrativeExpenses": 0,
        "sellingAndMarketingExpenses": 0,
        "sellingGeneralAndAdministrativeExpenses": 24932000000,
        "otherExpenses": 0,
        "operatingExpenses": 54847000000,
        "costAndExpenses": 268984000000,
        "interestIncome": 3750000000,
        "interestExpense": 3933000000,
        "depreciationAndAmortization": 11519000000,
        "ebitda": 125820000000,
        "ebitdaratio": 0.3283,
        "operatingIncome": 114301000000,
        "operatingIncomeRatio": 0.2982,
        "totalOtherIncomeExpensesNet": -565000000,
        "incomeBeforeTax": 113736000000,
        "incomeBeforeTaxRatio": 0.2967,
        "incomeTaxExpense": 16741000000,
        "netIncome": 96995000000,
        "netIncomeRatio": 0.2531,
        "eps": 6.16,
        "epsdiluted": 6.13,
        "weightedAverageShsOut": 15744231000,
        "weightedAverageShsOutDil": 15812547000,
        "link": "https://www.sec.gov/cgi-bin/viewer?action=view&cik=320193&accession_number=0000320193-23-000106&xbrl_type=v",
        "finalLink": "https://www.sec.gov/cgi-bin/viewer?action=view&cik=320193&accession_number=0000320193-23-000106&xbrl_type=v",
    }
]

# Mock Balance Sheet Response
MOCK_BALANCE_SHEET_RESPONSE: list[dict[str, Any]] = [
    {
        "date": "2023-09-30",
        "symbol": "AAPL",
        "reportedCurrency": "USD",
        "cik": "0000320193",
        "filingDate": "2023-11-03",
        "acceptedDate": "2023-11-02 18:01:13",
        "fiscalYear": "2023",
        "period": "FY",
        "cashAndCashEquivalents": 29965000000,
        "shortTermInvestments": 31590000000,
        "cashAndShortTermInvestments": 61555000000,
        "netReceivables": 60932000000,
        "inventory": 6511000000,
        "otherCurrentAssets": 14695000000,
        "totalCurrentAssets": 143566000000,
        "propertyPlantEquipmentNet": 43715000000,
        "goodwill": 0,
        "intangibleAssets": 0,
        "goodwillAndIntangibleAssets": 0,
        "longTermInvestments": 100544000000,
        "taxAssets": 0,
        "otherNonCurrentAssets": 64758000000,
        "totalNonCurrentAssets": 209017000000,
        "otherAssets": 0,
        "totalAssets": 352583000000,
        "accountPayables": 62611000000,
        "shortTermDebt": 15000000,
        "taxPayables": 0,
        "deferredRevenue": 8061000000,
        "otherCurrentLiabilities": 58829000000,
        "totalCurrentLiabilities": 133875000000,
        "longTermDebt": 95281000000,
        "deferredRevenueNonCurrent": 0,
        "deferredTaxLiabilitiesNonCurrent": 0,
        "otherNonCurrentLiabilities": 39441000000,
        "totalNonCurrentLiabilities": 134722000000,
        "otherLiabilities": 0,
        "capitalLeaseObligations": 0,
        "totalLiabilities": 268597000000,
        "preferredStock": 0,
        "commonStock": 73812000000,
        "retainedEarnings": 1408000000,
        "accumulatedOtherComprehensiveIncomeLoss": -11452000000,
        "othertotalStockholdersEquity": 81226000000,
        "totalStockholdersEquity": 62146000000,
        "totalEquity": 62146000000,
        "totalLiabilitiesAndStockholdersEquity": 352583000000,
        "minorityInterest": 0,
        "totalLiabilitiesAndTotalEquity": 352583000000,
        "totalInvestments": 132134000000,
        "totalDebt": 110296000000,
        "netDebt": 80331000000,
        "link": "https://www.sec.gov/cgi-bin/viewer?action=view&cik=320193&accession_number=0000320193-23-000106&xbrl_type=v",
        "finalLink": "https://www.sec.gov/cgi-bin/viewer?action=view&cik=320193&accession_number=0000320193-23-000106&xbrl_type=v",
    }
]

# Mock Cash Flow Statement Response
MOCK_CASH_FLOW_RESPONSE: list[dict[str, Any]] = [
    {
        "date": "2023-09-30",
        "symbol": "AAPL",
        "reportedCurrency": "USD",
        "cik": "0000320193",
        "filingDate": "2023-11-03",
        "acceptedDate": "2023-11-02 18:01:13",
        "fiscalYear": "2023",
        "period": "FY",
        "netIncome": 96995000000,
        "depreciationAndAmortization": 11519000000,
        "deferredIncomeTax": 0,
        "stockBasedCompensation": 10833000000,
        "changeInWorkingCapital": -6577000000,
        "accountsReceivables": -1688000000,
        "inventory": -1618000000,
        "accountsPayables": -1889000000,
        "otherWorkingCapital": -1382000000,
        "otherNonCashItems": -111000000,
        "netCashProvidedByOperatingActivities": 110543000000,
        "investmentsInPropertyPlantAndEquipment": -10959000000,
        "acquisitionsNet": -1683000000,
        "purchasesOfInvestments": -29513000000,
        "salesMaturitiesOfInvestments": 37446000000,
        "otherInvestingActivites": -1337000000,
        "netCashUsedForInvestingActivites": -6046000000,
        "debtRepayment": -11151000000,
        "commonStockIssued": 0,
        "commonStockRepurchased": -77550000000,
        "dividendsPaid": -15025000000,
        "otherFinancingActivites": 0,
        "netCashUsedProvidedByFinancingActivities": -103680000000,
        "effectOfForexChangesOnCash": 0,
        "netChangeInCash": 817000000,
        "cashAtEndOfPeriod": 29965000000,
        "cashAtBeginningOfPeriod": 29148000000,
        "operatingCashFlow": 110543000000,
        "capitalExpenditure": -10959000000,
        "freeCashFlow": 99584000000,
        "link": "https://www.sec.gov/cgi-bin/viewer?action=view&cik=320193&accession_number=0000320193-23-000106&xbrl_type=v",
        "finalLink": "https://www.sec.gov/cgi-bin/viewer?action=view&cik=320193&accession_number=0000320193-23-000106&xbrl_type=v",
    }
]

# Mock Key Metrics Response
MOCK_KEY_METRICS_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "date": "2023-09-30",
        "fiscalYear": "2023",
        "period": "FY",
        "revenuePerShare": 24.35,
        "netIncomePerShare": 6.16,
        "operatingCashFlowPerShare": 7.02,
        "freeCashFlowPerShare": 6.32,
        "cashPerShare": 1.90,
        "bookValuePerShare": 3.95,
        "tangibleBookValuePerShare": 3.95,
        "shareholdersEquityPerShare": 3.95,
        "interestDebtPerShare": 7.00,
        "marketCap": 2850000000000,
        "enterpriseValue": 2930000000000,
        "peRatio": 30.16,
        "priceToSalesRatio": 7.44,
        "pocfratio": 26.42,
        "pfcfRatio": 29.35,
        "pbRatio": 46.96,
        "ptbRatio": 46.96,
        "evToSales": 7.65,
        "enterpriseValueOverEBITDA": 23.29,
        "evToOperatingCashFlow": 26.51,
        "evToFreeCashFlow": 29.41,
        "earningsYield": 0.0332,
        "freeCashFlowYield": 0.0341,
        "debtToEquity": 1.77,
        "debtToAssets": 0.31,
        "netDebtToEBITDA": 0.64,
        "currentRatio": 1.07,
        "interestCoverage": 29.07,
        "incomeQuality": 1.14,
        "dividendYield": 0.0052,
        "payoutRatio": 0.1548,
        "salesGeneralAndAdministrativeToRevenue": 0.0651,
        "researchAndDevelopmentToRevenue": 0.0781,
        "intangiblesToTotalAssets": 0.0,
        "capexToOperatingCashFlow": 0.0991,
        "capexToRevenue": 0.0286,
        "capexToDepreciation": 0.9514,
        "stockBasedCompensationToRevenue": 0.0283,
        "grahamNumber": 37.85,
        "roic": 0.5815,
        "returnOnTangibleAssets": 0.3752,
        "grahamNetNet": -99.82,
        "workingCapital": 9691000000,
        "tangibleAssetValue": 62146000000,
        "netCurrentAssetValue": -190106000000,
        "investedCapital": 187442000000,
        "averageReceivables": 60500000000,
        "averagePayables": 62000000000,
        "averageInventory": 6500000000,
        "daysSalesOutstanding": 57.63,
        "daysPayablesOutstanding": 105.65,
        "daysOfInventoryOnHand": 11.07,
        "receivablesTurnover": 6.33,
        "payablesTurnover": 3.45,
        "inventoryTurnover": 32.95,
        "roe": 1.56,
        "capexPerShare": 0.70,
    }
]

# Mock Analyst Estimate Response
MOCK_ANALYST_ESTIMATE_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "date": "2024-03-31",
        "estimatedRevenueLow": 89000000000,
        "estimatedRevenueHigh": 94000000000,
        "estimatedRevenueAvg": 91500000000,
        "estimatedEbitdaLow": 28000000000,
        "estimatedEbitdaHigh": 31000000000,
        "estimatedEbitdaAvg": 29500000000,
        "estimatedEbitLow": 26000000000,
        "estimatedEbitHigh": 29000000000,
        "estimatedEbitAvg": 27500000000,
        "estimatedNetIncomeLow": 22000000000,
        "estimatedNetIncomeHigh": 25000000000,
        "estimatedNetIncomeAvg": 23500000000,
        "estimatedSgaExpenseLow": 5900000000,
        "estimatedSgaExpenseHigh": 6300000000,
        "estimatedSgaExpenseAvg": 6100000000,
        "estimatedEpsAvg": 1.53,
        "estimatedEpsHigh": 1.63,
        "estimatedEpsLow": 1.43,
        "numberAnalystEstimatedRevenue": 35,
        "numberAnalystEstimatedEps": 38,
    }
]

# Mock Price Target Response
MOCK_PRICE_TARGET_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "publishedDate": "2024-01-15",
        "newsURL": "https://www.example.com/analyst-report",
        "newsTitle": "Apple Inc. - Initiating Coverage with Buy Rating",
        "analystName": "John Smith",
        "analystCompany": "Goldman Sachs",
        "priceTarget": 210.0,
        "adjPriceTarget": 210.0,
        "priceWhenPosted": 185.50,
        "newsPublisher": "Goldman Sachs Research",
        "newsBaseURL": "example.com",
        "newsSentiment": "positive",
    }
]

# Mock Institutional Holder Response
MOCK_INSTITUTIONAL_HOLDER_RESPONSE: list[dict[str, Any]] = [
    {
        "holder": "Vanguard Group Inc",
        "shares": 1295805031,
        "dateReported": "2023-09-30",
        "change": 5123456,
        "percentHeld": 8.43,
        "value": 240000000000,
    },
    {
        "holder": "Blackrock Inc.",
        "shares": 1067859999,
        "dateReported": "2023-09-30",
        "change": -2345678,
        "percentHeld": 6.95,
        "value": 198000000000,
    },
]

# Mock News Response
MOCK_NEWS_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "publishedDate": "2024-01-23 10:30:00",
        "title": "Apple Reports Record Q1 Earnings",
        "image": "https://example.com/image.jpg",
        "site": "Reuters",
        "text": "Apple Inc. reported record first-quarter earnings today, beating analyst expectations...",
        "url": "https://www.reuters.com/technology/apple-earnings-2024",
    }
]

# Mock Dividend Response
MOCK_DIVIDEND_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "date": "2023-11-10",
        "label": "November 10, 23",
        "adjDividend": 0.24,
        "dividend": 0.24,
        "recordDate": "2023-11-13",
        "paymentDate": "2023-11-16",
        "declarationDate": "2023-11-02",
    },
    {
        "symbol": "AAPL",
        "date": "2023-08-11",
        "label": "August 11, 23",
        "adjDividend": 0.24,
        "dividend": 0.24,
        "recordDate": "2023-08-14",
        "paymentDate": "2023-08-17",
        "declarationDate": "2023-08-03",
    },
]

# Mock Earnings Transcript Response (simplified)
MOCK_TRANSCRIPT_RESPONSE: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "quarter": 1,
        "year": 2024,
        "date": "2024-02-01 16:30:00",
        "content": """Apple Inc. Q1 2024 Earnings Call Transcript

Operator: Good afternoon, and welcome to the Apple Q1 2024 Earnings Conference Call.

Tim Cook (CEO): Thank you for joining us today. I'm pleased to report record Q1 revenue of $119.6 billion, up 2% year over year. iPhone revenue was particularly strong at $69.7 billion...

Luca Maestri (CFO): Our operating margin expanded to 31.8%, up from 30.2% last year. We generated $39 billion in operating cash flow and returned $27 billion to shareholders...

Q&A Session

Analyst: Can you comment on the outlook for Services revenue?

Tim Cook: Services had another outstanding quarter with revenue of $23.1 billion, up 11% year over year. We see continued strong momentum across the App Store, Apple Music, iCloud, and our newer services...
""",
    }
]

# Error responses for testing
MOCK_404_ERROR = {"error": "Symbol not found"}
MOCK_429_ERROR = {"error": "Rate limit exceeded. Please try again later."}
MOCK_403_ERROR = {"error": "This endpoint requires a higher tier subscription"}
