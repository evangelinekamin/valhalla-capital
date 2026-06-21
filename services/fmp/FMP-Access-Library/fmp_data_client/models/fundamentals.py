"""Fundamental financial data models - statements, metrics, ratios, scores."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import Field

from .base import FMPBaseModel


class IncomeStatement(FMPBaseModel):
    """Income statement data."""

    # Metadata
    symbol: str = Field(..., description="Stock ticker symbol")
    period_date: date = Field(..., alias="date", description="Fiscal period end date")
    period: str = Field(..., description="Period type (Q1, Q2, FY, etc.)")
    calendar_year: Optional[str] = Field(
        None,
        alias="fiscalYear",
        description="Calendar year"
    )
    filing_date: Optional[date] = Field(
        None,
        alias="filingDate",
        description="SEC filing date"
    )
    accepted_date: Optional[datetime] = Field(
        None,
        alias="acceptedDate",
        description="Date and time accepted by SEC"
    )

    # Revenue
    revenue: Optional[float] = Field(None, description="Total revenue")
    cost_of_revenue: Optional[float] = Field(
        None,
        alias="costOfRevenue",
        description="Cost of revenue"
    )
    gross_profit: Optional[float] = Field(
        None,
        alias="grossProfit",
        description="Gross profit"
    )
    gross_profit_ratio: Optional[float] = Field(
        None,
        alias="grossProfitRatio",
        description="Gross profit margin"
    )

    # Operating expenses
    research_and_development: Optional[float] = Field(
        None,
        alias="researchAndDevelopmentExpenses",
        description="R&D expenses"
    )
    general_and_administrative: Optional[float] = Field(
        None,
        alias="generalAndAdministrativeExpenses",
        description="G&A expenses"
    )
    selling_and_marketing: Optional[float] = Field(
        None,
        alias="sellingAndMarketingExpenses",
        description="Sales & marketing expenses"
    )
    selling_general_admin: Optional[float] = Field(
        None,
        alias="sellingGeneralAndAdministrativeExpenses",
        description="SG&A expenses"
    )
    other_expenses: Optional[float] = Field(
        None,
        alias="otherExpenses",
        description="Other expenses"
    )
    operating_expenses: Optional[float] = Field(
        None,
        alias="operatingExpenses",
        description="Total operating expenses"
    )
    cost_and_expenses: Optional[float] = Field(
        None,
        alias="costAndExpenses",
        description="Total costs and expenses"
    )

    # Operating income
    operating_income: Optional[float] = Field(
        None,
        alias="operatingIncome",
        description="Operating income (EBIT)"
    )
    operating_income_ratio: Optional[float] = Field(
        None,
        alias="operatingIncomeRatio",
        description="Operating margin"
    )

    # Interest and other income/expense
    interest_income: Optional[float] = Field(
        None,
        alias="interestIncome",
        description="Interest income"
    )
    interest_expense: Optional[float] = Field(
        None,
        alias="interestExpense",
        description="Interest expense"
    )
    depreciation_and_amortization: Optional[float] = Field(
        None,
        alias="depreciationAndAmortization",
        description="D&A"
    )

    # EBITDA
    ebitda: Optional[float] = Field(None, description="EBITDA")
    ebitda_ratio: Optional[float] = Field(
        None,
        alias="ebitdaratio",
        description="EBITDA margin"
    )

    # Pre-tax income
    total_other_income: Optional[float] = Field(
        None,
        alias="totalOtherIncomeExpensesNet",
        description="Other income/expenses net"
    )
    income_before_tax: Optional[float] = Field(
        None,
        alias="incomeBeforeTax",
        description="Income before tax"
    )
    income_before_tax_ratio: Optional[float] = Field(
        None,
        alias="incomeBeforeTaxRatio",
        description="Pre-tax margin"
    )

    # Taxes
    income_tax_expense: Optional[float] = Field(
        None,
        alias="incomeTaxExpense",
        description="Income tax expense"
    )

    # Net income
    net_income: Optional[float] = Field(
        None,
        alias="netIncome",
        description="Net income"
    )
    net_income_ratio: Optional[float] = Field(
        None,
        alias="netIncomeRatio",
        description="Net profit margin"
    )

    # EPS
    eps: Optional[float] = Field(None, description="Basic EPS")
    eps_diluted: Optional[float] = Field(
        None,
        alias="epsdiluted",
        description="Diluted EPS"
    )

    # Shares
    weighted_average_shares: Optional[float] = Field(
        None,
        alias="weightedAverageShsOut",
        description="Weighted average shares outstanding"
    )
    weighted_average_shares_diluted: Optional[float] = Field(
        None,
        alias="weightedAverageShsOutDil",
        description="Weighted average diluted shares"
    )

    # Link to filing
    link: Optional[str] = Field(None, description="Link to SEC filing")
    final_link: Optional[str] = Field(
        None,
        alias="finalLink",
        description="Final link to filing"
    )


class BalanceSheet(FMPBaseModel):
    """Balance sheet data."""

    # Metadata
    symbol: str = Field(..., description="Stock ticker symbol")
    period_date: date = Field(..., alias="date", description="Fiscal period end date")
    period: str = Field(..., description="Period type")
    calendar_year: Optional[str] = Field(
        None,
        alias="fiscalYear",
        description="Calendar year"
    )
    filing_date: Optional[date] = Field(
        None,
        alias="filingDate",
        description="Filing date"
    )
    accepted_date: Optional[datetime] = Field(
        None,
        alias="acceptedDate",
        description="Accepted date and time"
    )

    # Assets - Current
    cash_and_equivalents: Optional[float] = Field(
        None,
        alias="cashAndCashEquivalents",
        description="Cash and cash equivalents"
    )
    short_term_investments: Optional[float] = Field(
        None,
        alias="shortTermInvestments",
        description="Short-term investments"
    )
    cash_and_short_term_investments: Optional[float] = Field(
        None,
        alias="cashAndShortTermInvestments",
        description="Total cash and investments"
    )
    receivables: Optional[float] = Field(
        None,
        alias="netReceivables",
        description="Accounts receivable"
    )
    inventory: Optional[float] = Field(None, description="Inventory")
    other_current_assets: Optional[float] = Field(
        None,
        alias="otherCurrentAssets",
        description="Other current assets"
    )
    total_current_assets: Optional[float] = Field(
        None,
        alias="totalCurrentAssets",
        description="Total current assets"
    )

    # Assets - Long-term
    property_plant_equipment: Optional[float] = Field(
        None,
        alias="propertyPlantEquipmentNet",
        description="PP&E net"
    )
    goodwill: Optional[float] = Field(None, description="Goodwill")
    intangible_assets: Optional[float] = Field(
        None,
        alias="intangibleAssets",
        description="Intangible assets"
    )
    goodwill_and_intangible_assets: Optional[float] = Field(
        None,
        alias="goodwillAndIntangibleAssets",
        description="Total goodwill and intangibles"
    )
    long_term_investments: Optional[float] = Field(
        None,
        alias="longTermInvestments",
        description="Long-term investments"
    )
    tax_assets: Optional[float] = Field(
        None,
        alias="taxAssets",
        description="Tax assets"
    )
    other_non_current_assets: Optional[float] = Field(
        None,
        alias="otherNonCurrentAssets",
        description="Other non-current assets"
    )
    total_non_current_assets: Optional[float] = Field(
        None,
        alias="totalNonCurrentAssets",
        description="Total non-current assets"
    )

    # Total assets
    total_assets: Optional[float] = Field(
        None,
        alias="totalAssets",
        description="Total assets"
    )

    # Liabilities - Current
    accounts_payable: Optional[float] = Field(
        None,
        alias="accountPayables",
        description="Accounts payable"
    )
    short_term_debt: Optional[float] = Field(
        None,
        alias="shortTermDebt",
        description="Short-term debt"
    )
    tax_payables: Optional[float] = Field(
        None,
        alias="taxPayables",
        description="Tax payables"
    )
    deferred_revenue: Optional[float] = Field(
        None,
        alias="deferredRevenue",
        description="Deferred revenue"
    )
    other_current_liabilities: Optional[float] = Field(
        None,
        alias="otherCurrentLiabilities",
        description="Other current liabilities"
    )
    total_current_liabilities: Optional[float] = Field(
        None,
        alias="totalCurrentLiabilities",
        description="Total current liabilities"
    )

    # Liabilities - Long-term
    long_term_debt: Optional[float] = Field(
        None,
        alias="longTermDebt",
        description="Long-term debt"
    )
    deferred_revenue_non_current: Optional[float] = Field(
        None,
        alias="deferredRevenueNonCurrent",
        description="Deferred revenue non-current"
    )
    deferred_tax_liabilities: Optional[float] = Field(
        None,
        alias="deferredTaxLiabilitiesNonCurrent",
        description="Deferred tax liabilities"
    )
    other_non_current_liabilities: Optional[float] = Field(
        None,
        alias="otherNonCurrentLiabilities",
        description="Other non-current liabilities"
    )
    total_non_current_liabilities: Optional[float] = Field(
        None,
        alias="totalNonCurrentLiabilities",
        description="Total non-current liabilities"
    )

    # Total liabilities
    total_liabilities: Optional[float] = Field(
        None,
        alias="totalLiabilities",
        description="Total liabilities"
    )

    # Equity
    common_stock: Optional[float] = Field(
        None,
        alias="commonStock",
        description="Common stock"
    )
    retained_earnings: Optional[float] = Field(
        None,
        alias="retainedEarnings",
        description="Retained earnings"
    )
    accumulated_other_comprehensive_income: Optional[float] = Field(
        None,
        alias="accumulatedOtherComprehensiveIncomeLoss",
        description="Accumulated OCI"
    )
    other_total_stockholders_equity: Optional[float] = Field(
        None,
        alias="othertotalStockholdersEquity",
        description="Other stockholders equity"
    )
    total_stockholders_equity: Optional[float] = Field(
        None,
        alias="totalStockholdersEquity",
        description="Total stockholders equity"
    )

    # Total equity
    total_equity: Optional[float] = Field(
        None,
        alias="totalEquity",
        description="Total equity"
    )

    # Total liabilities and equity
    total_liabilities_and_equity: Optional[float] = Field(
        None,
        alias="totalLiabilitiesAndStockholdersEquity",
        description="Total liabilities and equity"
    )

    # Shares outstanding
    total_investments: Optional[float] = Field(
        None,
        alias="totalInvestments",
        description="Total investments"
    )
    total_debt: Optional[float] = Field(
        None,
        alias="totalDebt",
        description="Total debt"
    )
    net_debt: Optional[float] = Field(
        None,
        alias="netDebt",
        description="Net debt"
    )

    # Link
    link: Optional[str] = Field(None, description="Link to filing")
    final_link: Optional[str] = Field(
        None,
        alias="finalLink",
        description="Final link"
    )


class CashFlowStatement(FMPBaseModel):
    """Cash flow statement data."""

    # Metadata
    symbol: str = Field(..., description="Stock ticker symbol")
    period_date: date = Field(..., alias="date", description="Fiscal period end date")
    period: str = Field(..., description="Period type")
    calendar_year: Optional[str] = Field(
        None,
        alias="fiscalYear",
        description="Calendar year"
    )
    filing_date: Optional[date] = Field(
        None,
        alias="filingDate",
        description="Filing date"
    )
    accepted_date: Optional[datetime] = Field(
        None,
        alias="acceptedDate",
        description="Accepted date and time"
    )

    # Operating activities
    net_income: Optional[float] = Field(
        None,
        alias="netIncome",
        description="Net income"
    )
    depreciation_and_amortization: Optional[float] = Field(
        None,
        alias="depreciationAndAmortization",
        description="D&A"
    )
    deferred_income_tax: Optional[float] = Field(
        None,
        alias="deferredIncomeTax",
        description="Deferred income tax"
    )
    stock_based_compensation: Optional[float] = Field(
        None,
        alias="stockBasedCompensation",
        description="Stock-based compensation"
    )
    change_in_working_capital: Optional[float] = Field(
        None,
        alias="changeInWorkingCapital",
        description="Change in working capital"
    )
    accounts_receivables: Optional[float] = Field(
        None,
        alias="accountsReceivables",
        description="Change in accounts receivable"
    )
    inventory_change: Optional[float] = Field(
        None,
        alias="inventory",
        description="Change in inventory"
    )
    accounts_payables: Optional[float] = Field(
        None,
        alias="accountsPayables",
        description="Change in accounts payable"
    )
    other_working_capital: Optional[float] = Field(
        None,
        alias="otherWorkingCapital",
        description="Other working capital changes"
    )
    other_non_cash_items: Optional[float] = Field(
        None,
        alias="otherNonCashItems",
        description="Other non-cash items"
    )
    net_cash_from_operating: Optional[float] = Field(
        None,
        alias="netCashProvidedByOperatingActivities",
        description="Net cash from operating activities"
    )

    # Investing activities
    investments_in_property: Optional[float] = Field(
        None,
        alias="investmentsInPropertyPlantAndEquipment",
        description="Capital expenditures"
    )
    acquisitions_net: Optional[float] = Field(
        None,
        alias="acquisitionsNet",
        description="Acquisitions net"
    )
    purchases_of_investments: Optional[float] = Field(
        None,
        alias="purchasesOfInvestments",
        description="Purchases of investments"
    )
    sales_maturities_of_investments: Optional[float] = Field(
        None,
        alias="salesMaturitiesOfInvestments",
        description="Sales/maturities of investments"
    )
    other_investing_activities: Optional[float] = Field(
        None,
        alias="otherInvestingActivites",
        description="Other investing activities"
    )
    net_cash_from_investing: Optional[float] = Field(
        None,
        alias="netCashUsedForInvestingActivites",
        description="Net cash from investing activities"
    )

    # Financing activities
    debt_repayment: Optional[float] = Field(
        None,
        alias="debtRepayment",
        description="Debt repayment"
    )
    common_stock_issued: Optional[float] = Field(
        None,
        alias="commonStockIssued",
        description="Common stock issued"
    )
    common_stock_repurchased: Optional[float] = Field(
        None,
        alias="commonStockRepurchased",
        description="Common stock repurchased"
    )
    dividends_paid: Optional[float] = Field(
        None,
        alias="dividendsPaid",
        description="Dividends paid"
    )
    other_financing_activities: Optional[float] = Field(
        None,
        alias="otherFinancingActivites",
        description="Other financing activities"
    )
    net_cash_from_financing: Optional[float] = Field(
        None,
        alias="netCashUsedProvidedByFinancingActivities",
        description="Net cash from financing activities"
    )

    # Effect of forex
    effect_of_forex: Optional[float] = Field(
        None,
        alias="effectOfForexChangesOnCash",
        description="Effect of forex on cash"
    )

    # Net change in cash
    net_change_in_cash: Optional[float] = Field(
        None,
        alias="netChangeInCash",
        description="Net change in cash"
    )

    # Beginning and ending cash
    cash_at_beginning: Optional[float] = Field(
        None,
        alias="cashAtBeginningOfPeriod",
        description="Cash at beginning of period"
    )
    cash_at_end: Optional[float] = Field(
        None,
        alias="cashAtEndOfPeriod",
        description="Cash at end of period"
    )

    # Operating cash flow
    operating_cash_flow: Optional[float] = Field(
        None,
        alias="operatingCashFlow",
        description="Operating cash flow"
    )
    capital_expenditure: Optional[float] = Field(
        None,
        alias="capitalExpenditure",
        description="Capital expenditure"
    )
    free_cash_flow: Optional[float] = Field(
        None,
        alias="freeCashFlow",
        description="Free cash flow"
    )

    # Link
    link: Optional[str] = Field(None, description="Link to filing")
    final_link: Optional[str] = Field(
        None,
        alias="finalLink",
        description="Final link"
    )


class KeyMetrics(FMPBaseModel):
    """Key financial metrics."""

    symbol: str = Field(..., description="Stock ticker symbol")
    period_date: date = Field(..., alias="date", description="Date")
    period: Optional[str] = Field(None, description="Period")
    calendar_year: Optional[str] = Field(
        None,
        alias="fiscalYear",
        description="Calendar year"
    )

    # Valuation metrics
    revenue_per_share: Optional[float] = Field(
        None,
        alias="revenuePerShare",
        description="Revenue per share"
    )
    net_income_per_share: Optional[float] = Field(
        None,
        alias="netIncomePerShare",
        description="Net income per share"
    )
    operating_cash_flow_per_share: Optional[float] = Field(
        None,
        alias="operatingCashFlowPerShare",
        description="Operating cash flow per share"
    )
    free_cash_flow_per_share: Optional[float] = Field(
        None,
        alias="freeCashFlowPerShare",
        description="Free cash flow per share"
    )
    cash_per_share: Optional[float] = Field(
        None,
        alias="cashPerShare",
        description="Cash per share"
    )
    book_value_per_share: Optional[float] = Field(
        None,
        alias="bookValuePerShare",
        description="Book value per share"
    )
    tangible_book_value_per_share: Optional[float] = Field(
        None,
        alias="tangibleBookValuePerShare",
        description="Tangible book value per share"
    )
    shareholders_equity_per_share: Optional[float] = Field(
        None,
        alias="shareholdersEquityPerShare",
        description="Shareholders equity per share"
    )

    # Valuation ratios
    market_cap: Optional[float] = Field(
        None,
        alias="marketCap",
        description="Market capitalization"
    )
    enterprise_value: Optional[float] = Field(
        None,
        alias="enterpriseValue",
        description="Enterprise value"
    )
    pe_ratio: Optional[float] = Field(
        None,
        alias="peRatio",
        description="P/E ratio"
    )
    price_to_sales: Optional[float] = Field(
        None,
        alias="priceToSalesRatio",
        description="Price to sales"
    )
    price_to_book: Optional[float] = Field(
        None,
        alias="pbRatio",
        description="Price to book"
    )
    ptb_ratio: Optional[float] = Field(
        None,
        alias="ptbRatio",
        description="Price to tangible book"
    )
    ev_to_sales: Optional[float] = Field(
        None,
        alias="evToSales",
        description="EV to sales"
    )
    ev_to_ebitda: Optional[float] = Field(
        None,
        alias="enterpriseValueOverEBITDA",
        description="EV to EBITDA"
    )
    ev_to_operating_cash_flow: Optional[float] = Field(
        None,
        alias="evToOperatingCashFlow",
        description="EV to operating cash flow"
    )
    ev_to_free_cash_flow: Optional[float] = Field(
        None,
        alias="evToFreeCashFlow",
        description="EV to free cash flow"
    )

    # Efficiency metrics
    earnings_yield: Optional[float] = Field(
        None,
        alias="earningsYield",
        description="Earnings yield"
    )
    free_cash_flow_yield: Optional[float] = Field(
        None,
        alias="freeCashFlowYield",
        description="Free cash flow yield"
    )
    debt_to_equity: Optional[float] = Field(
        None,
        alias="debtToEquity",
        description="Debt to equity"
    )
    debt_to_assets: Optional[float] = Field(
        None,
        alias="debtToAssets",
        description="Debt to assets"
    )
    net_debt_to_ebitda: Optional[float] = Field(
        None,
        alias="netDebtToEBITDA",
        description="Net debt to EBITDA"
    )
    current_ratio: Optional[float] = Field(
        None,
        alias="currentRatio",
        description="Current ratio"
    )
    interest_coverage: Optional[float] = Field(
        None,
        alias="interestCoverage",
        description="Interest coverage"
    )
    income_quality: Optional[float] = Field(
        None,
        alias="incomeQuality",
        description="Income quality"
    )

    # Growth metrics
    revenue_growth: Optional[float] = Field(
        None,
        alias="revenueGrowth",
        description="Revenue growth"
    )
    eps_growth: Optional[float] = Field(
        None,
        alias="epsGrowth",
        description="EPS growth"
    )

    # Profitability metrics
    roe: Optional[float] = Field(
        None,
        alias="roe",
        description="Return on equity"
    )
    roa: Optional[float] = Field(
        None,
        alias="returnOnTangibleAssets",
        description="Return on tangible assets"
    )
    roic: Optional[float] = Field(
        None,
        alias="roic",
        description="Return on invested capital"
    )

    # Dividend metrics
    dividend_yield: Optional[float] = Field(
        None,
        alias="dividendYield",
        description="Dividend yield"
    )
    payout_ratio: Optional[float] = Field(
        None,
        alias="payoutRatio",
        description="Payout ratio"
    )

    # Other
    shares_outstanding: Optional[float] = Field(
        None,
        alias="sharesOutstanding",
        description="Shares outstanding"
    )


class FinancialRatios(FMPBaseModel):
    """Comprehensive financial ratios."""

    symbol: str = Field(..., description="Stock ticker symbol")
    period_date: date = Field(..., alias="date", description="Date")
    period: Optional[str] = Field(None, description="Period")
    calendar_year: Optional[str] = Field(
        None,
        alias="fiscalYear",
        description="Calendar year"
    )

    # Liquidity ratios
    current_ratio: Optional[float] = Field(
        None,
        alias="currentRatio",
        description="Current ratio"
    )
    quick_ratio: Optional[float] = Field(
        None,
        alias="quickRatio",
        description="Quick ratio"
    )
    cash_ratio: Optional[float] = Field(
        None,
        alias="cashRatio",
        description="Cash ratio"
    )

    # Leverage ratios
    debt_ratio: Optional[float] = Field(
        None,
        alias="debtRatio",
        description="Debt ratio"
    )
    debt_equity_ratio: Optional[float] = Field(
        None,
        alias="debtEquityRatio",
        description="Debt to equity"
    )
    long_term_debt_to_capitalization: Optional[float] = Field(
        None,
        alias="longTermDebtToCapitalization",
        description="Long-term debt to capitalization"
    )
    total_debt_to_capitalization: Optional[float] = Field(
        None,
        alias="totalDebtToCapitalization",
        description="Total debt to capitalization"
    )
    interest_coverage: Optional[float] = Field(
        None,
        alias="interestCoverage",
        description="Interest coverage"
    )
    cash_flow_to_debt_ratio: Optional[float] = Field(
        None,
        alias="cashFlowToDebtRatio",
        description="Cash flow to debt"
    )

    # Profitability ratios
    gross_profit_margin: Optional[float] = Field(
        None,
        alias="grossProfitMargin",
        description="Gross profit margin"
    )
    operating_profit_margin: Optional[float] = Field(
        None,
        alias="operatingProfitMargin",
        description="Operating profit margin"
    )
    pretax_profit_margin: Optional[float] = Field(
        None,
        alias="pretaxProfitMargin",
        description="Pre-tax profit margin"
    )
    net_profit_margin: Optional[float] = Field(
        None,
        alias="netProfitMargin",
        description="Net profit margin"
    )
    effective_tax_rate: Optional[float] = Field(
        None,
        alias="effectiveTaxRate",
        description="Effective tax rate"
    )

    # Return ratios
    return_on_assets: Optional[float] = Field(
        None,
        alias="returnOnAssets",
        description="Return on assets (ROA)"
    )
    return_on_equity: Optional[float] = Field(
        None,
        alias="returnOnEquity",
        description="Return on equity (ROE)"
    )
    return_on_capital_employed: Optional[float] = Field(
        None,
        alias="returnOnCapitalEmployed",
        description="Return on capital employed (ROCE)"
    )

    # Efficiency ratios
    asset_turnover: Optional[float] = Field(
        None,
        alias="assetTurnover",
        description="Asset turnover"
    )
    inventory_turnover: Optional[float] = Field(
        None,
        alias="inventoryTurnover",
        description="Inventory turnover"
    )
    receivables_turnover: Optional[float] = Field(
        None,
        alias="receivablesTurnover",
        description="Receivables turnover"
    )
    days_sales_outstanding: Optional[float] = Field(
        None,
        alias="daysSalesOutstanding",
        description="Days sales outstanding"
    )
    days_inventory_outstanding: Optional[float] = Field(
        None,
        alias="daysOfInventoryOutstanding",
        description="Days inventory outstanding"
    )
    days_payables_outstanding: Optional[float] = Field(
        None,
        alias="daysOfPayablesOutstanding",
        description="Days payables outstanding"
    )
    cash_conversion_cycle: Optional[float] = Field(
        None,
        alias="cashConversionCycle",
        description="Cash conversion cycle"
    )

    # Market ratios
    price_earnings_ratio: Optional[float] = Field(
        None,
        alias="priceEarningsRatio",
        description="P/E ratio"
    )
    price_to_book_ratio: Optional[float] = Field(
        None,
        alias="priceToBookRatio",
        description="Price to book"
    )
    price_to_sales_ratio: Optional[float] = Field(
        None,
        alias="priceToSalesRatio",
        description="Price to sales"
    )
    price_cash_flow_ratio: Optional[float] = Field(
        None,
        alias="priceCashFlowRatio",
        description="Price to cash flow"
    )
    price_earnings_to_growth: Optional[float] = Field(
        None,
        alias="priceEarningsToGrowthRatio",
        description="PEG ratio"
    )
    dividend_yield: Optional[float] = Field(
        None,
        alias="dividendYield",
        description="Dividend yield"
    )
    payout_ratio: Optional[float] = Field(
        None,
        alias="payoutRatio",
        description="Payout ratio"
    )


class FinancialScores(FMPBaseModel):
    """Financial health scores."""

    symbol: str = Field(..., description="Stock ticker symbol")
    period_date: date = Field(..., alias="date", description="Date")

    # Piotroski F-Score (0-9)
    piotroski_score: Optional[int] = Field(
        None,
        alias="piotroskiScore",
        description="Piotroski F-Score (0-9)"
    )

    # Altman Z-Score
    altman_z_score: Optional[float] = Field(
        None,
        alias="altmanZScore",
        description="Altman Z-Score"
    )

    @property
    def piotroski_strength(self) -> Optional[str]:
        """Get Piotroski score strength interpretation.

        Returns:
            Strength interpretation or None
        """
        if self.piotroski_score is None:
            return None
        if self.piotroski_score >= 8:
            return "Very Strong"
        elif self.piotroski_score >= 6:
            return "Strong"
        elif self.piotroski_score >= 4:
            return "Moderate"
        else:
            return "Weak"

    @property
    def altman_interpretation(self) -> Optional[str]:
        """Get Altman Z-Score interpretation.

        Returns:
            Bankruptcy risk interpretation or None
        """
        if self.altman_z_score is None:
            return None
        if self.altman_z_score > 2.99:
            return "Safe Zone (Low bankruptcy risk)"
        elif self.altman_z_score >= 1.81:
            return "Grey Zone (Moderate risk)"
        else:
            return "Distress Zone (High bankruptcy risk)"
