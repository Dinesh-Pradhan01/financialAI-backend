from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Executive Scorecard
# ---------------------------------------------------------------------------

class ExecutiveScorecardItem(BaseModel):
    analytical_module: str = Field(..., description="Module name e.g. Statement Verification")
    key_indicator: str = Field(..., description="Metric key e.g. Ending Cash Balance")
    current_value: str = Field(..., description="Formatted value string e.g. ₹8,640,655.54")
    assessment: str = Field(..., description="Assessment note e.g. Strong liquidity reserve")

# ---------------------------------------------------------------------------
# Section 1: Header Metadata
# ---------------------------------------------------------------------------

class HeaderMetadataResponse(BaseModel):
    bank_name: str = Field("State Bank of India", description="Bank Name")
    account_holder_name: str = Field("Nimbus Logistics Solutions Pvt Ltd", description="Account Holder Name")
    account_number: str = Field("····3421", description="Account Number (Masked/Raw)")
    account_type: str = Field("Current Account", description="Account Type")
    ifsc_code_branch: str = Field("SBIN0001234 (Main Branch, Bengaluru)", description="IFSC Code / Branch")
    statement_coverage_period: str = Field("01-Jan-2026 to 30-Jun-2026", description="Coverage Period")
    opening_balance: float = Field(6683000.0, description="Opening Balance")
    closing_balance: float = Field(8640655.54, description="Closing Balance")

# ---------------------------------------------------------------------------
# Section 2: Macro Cash Flow & Liquidity
# ---------------------------------------------------------------------------

class MonthlyCashFlowRow(BaseModel):
    month: str
    inflow_credits: float
    outflow_debits: float
    net_cash_flow: float
    ending_balance: float
    outflow_burn_rate: float

class LiquidityDiagnostics(BaseModel):
    avg_monthly_outflow_burn: float
    cash_runway_months: float
    liquidity_buffer_ratio: float
    safety_reserve_3_month: float
    idle_cash_available: float
    cash_conversion_retention_pct: float

class MacroCashFlowResponse(BaseModel):
    monthly_cash_flow_trajectory: List[MonthlyCashFlowRow]
    liquidity_diagnostics: LiquidityDiagnostics

# ---------------------------------------------------------------------------
# Section 3: Time-Based & Temporal Patterns
# ---------------------------------------------------------------------------

class DayRangeDistribution(BaseModel):
    day_range: str
    cumulative_inflows: float
    cumulative_outflows: float
    dominant_activity: str

class MonthEndLiquidityDip(BaseModel):
    month: str
    disbursement_day: str
    pre_payout_balance: float
    post_payout_balance: float
    instant_liquidity_dip: float

class DayOfWeekSpend(BaseModel):
    day_of_week: str
    spend_volume: float
    outflow_share_pct: float

class TemporalPatternsResponse(BaseModel):
    day_of_month_distribution: List[DayRangeDistribution]
    month_end_liquidity_dips: List[MonthEndLiquidityDip]
    day_of_week_spend: List[DayOfWeekSpend]

# ---------------------------------------------------------------------------
# Section 4: Transaction Channel & Payment Method Distribution
# ---------------------------------------------------------------------------

class ChannelDistributionItem(BaseModel):
    payment_channel: str
    description: str
    transaction_count: int
    total_volume: float
    share_of_outflows_pct: float

class ChannelDistributionResponse(BaseModel):
    channels: List[ChannelDistributionItem]
    total_transactions: int
    total_volume: float

# ---------------------------------------------------------------------------
# Section 5: Pure Anomaly, Risk & Domain Outliers
# Note: Statement Arithmetic Check & Round-Number Anomalies have been removed.
# ---------------------------------------------------------------------------

class StatisticalOutlierItem(BaseModel):
    transaction_date: str
    domain_category: str
    narration_snippet: str
    amount: float
    category_average_spend: float
    z_score: str
    assessment: str

class DuplicateTransactionItem(BaseModel):
    transaction_date: str
    amount: float
    narration: str
    reference_number: Optional[str] = ""
    duplicate_count: int = 2

class AnomalyRiskResponse(BaseModel):
    statistical_outliers: List[StatisticalOutlierItem]
    duplicate_transactions: List[DuplicateTransactionItem]
    total_outliers_found: int
    total_duplicates_found: int

# ---------------------------------------------------------------------------
# Section 6: Financial Efficiency & Projections
# ---------------------------------------------------------------------------

class OperationalEfficiencyRatios(BaseModel):
    inflow_to_outflow_ratio: float
    cost_to_income_ratio_pct: float
    net_cash_margin_proxy_pct: float

class ProjectionsAndRunRates(BaseModel):
    annualized_inflow_run_rate: float
    annualized_outflow_run_rate: float
    projected_next_month_ending_balance: float

class EfficiencyProjectionsResponse(BaseModel):
    operational_efficiency: OperationalEfficiencyRatios
    projections: ProjectionsAndRunRates

# ---------------------------------------------------------------------------
# Full Combined Report
# ---------------------------------------------------------------------------

class SpotliteFullReport(BaseModel):
    company_name: str
    period: str
    total_transactions_analyzed: int
    executive_summary: List[ExecutiveScorecardItem]
    section_1_header_metadata: HeaderMetadataResponse
    section_2_macro_cash_flow: MacroCashFlowResponse
    section_3_temporal_patterns: TemporalPatternsResponse
    section_4_channel_distribution: ChannelDistributionResponse
    section_5_anomaly_risk: AnomalyRiskResponse
    section_6_efficiency_projections: EfficiencyProjectionsResponse
