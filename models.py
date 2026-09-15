from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


STAGING_SCHEMA = "STG.Marketing"


class Base(DeclarativeBase):
    pass


class Ad(Base):
    __tablename__ = "Ad"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AdID: Mapped[int] = mapped_column(BigInteger, primary_key=True,autoincrement=False)
    AdAccountID: Mapped[int] = mapped_column(BigInteger, nullable=False)
    CampaignID: Mapped[int | None] = mapped_column(BigInteger)
    AdSetID: Mapped[int | None] = mapped_column(BigInteger)
    CreativeID: Mapped[int | None] = mapped_column(BigInteger)
    AdName: Mapped[str | None] = mapped_column(String(500))
    Status: Mapped[str | None] = mapped_column(String(100))
    ConfiguredStatus: Mapped[str | None] = mapped_column(String(100))
    EffectiveStatus: Mapped[str | None] = mapped_column(String(100))
    AdActiveTime: Mapped[int | None] = mapped_column(Integer)
    SourceAdID: Mapped[int | None] = mapped_column(BigInteger)
    EffectiveObjectStoryID: Mapped[str | None] = mapped_column(String(500))
    ObjectStoryID: Mapped[str | None] = mapped_column(String(500))
    ScheduledStartTime: Mapped[datetime | None] = mapped_column(DateTime)
    ScheduledEndTime: Mapped[datetime | None] = mapped_column(DateTime)
    CreatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    UpdatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class AdAccount(Base):
    __tablename__ = "AdAccount"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AccountID: Mapped[str] = mapped_column(String(500), primary_key=True, autoincrement=False)
    AccountName: Mapped[str | None] = mapped_column(String(500))
    AccountStatus: Mapped[int | None] = mapped_column(Integer)
    DisableReason: Mapped[int | None] = mapped_column(Integer)
    Currency: Mapped[str | None] = mapped_column(String(50))
    TimezoneName: Mapped[str | None] = mapped_column(String(200))
    TimezoneOffsetHrsUtc: Mapped[float | None] = mapped_column(Numeric(5, 2))
    AmountSpent: Mapped[float | None] = mapped_column(Numeric(18, 2))
    Balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    SpendCap: Mapped[float | None] = mapped_column(Numeric(18, 2))
    MinCampaignGroupSpendCap: Mapped[float | None] = mapped_column(Numeric(18, 2))
    MinDailyBudget: Mapped[float | None] = mapped_column(Numeric(18, 2))
    IsPersonal: Mapped[bool | None] = mapped_column(Boolean)
    BusinessID: Mapped[int | None] = mapped_column(BigInteger)
    FundingSourceID: Mapped[int | None] = mapped_column(BigInteger)
    FundingSourceDisplayString: Mapped[str | None] = mapped_column(String(500))
    FundingSourceType: Mapped[int | None] = mapped_column(Integer)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class AdInsightsDaily(Base):
    __tablename__ = "AdInsightsDaily"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AdID: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    DateKey: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    AdSetID: Mapped[int | None] = mapped_column(BigInteger)
    CampaignID: Mapped[int | None] = mapped_column(BigInteger)
    AdAccountID: Mapped[int] = mapped_column(BigInteger, nullable=False)
    Date: Mapped[datetime] = mapped_column(Date, nullable=False)
    Impressions: Mapped[int | None] = mapped_column(BigInteger)
    Reach: Mapped[int | None] = mapped_column(BigInteger)
    Frequency: Mapped[float | None] = mapped_column(Numeric(18, 6))
    Spend: Mapped[float | None] = mapped_column(Numeric(18, 2))
    SocialSpend: Mapped[float | None] = mapped_column(Numeric(18, 2))
    Clicks: Mapped[int | None] = mapped_column(BigInteger)
    UniqueClicks: Mapped[int | None] = mapped_column(BigInteger)
    CPC: Mapped[float | None] = mapped_column(Numeric(18, 6))
    CPP: Mapped[float | None] = mapped_column(Numeric(18, 6))
    InlineLinkClicks: Mapped[int | None] = mapped_column(BigInteger)
    InlineLinkClickCTR: Mapped[float | None] = mapped_column(Numeric(18, 6))
    CostPerInlineLinkClick: Mapped[float | None] = mapped_column(Numeric(18, 6))
    InlinePostEngagement: Mapped[int | None] = mapped_column(BigInteger)
    CostPerInlinePostEngagement: Mapped[float | None] = mapped_column(Numeric(18, 6))
    Leads: Mapped[int | None] = mapped_column(BigInteger)
    CostPerLead: Mapped[float | None] = mapped_column(Numeric(18, 6))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class AdSet(Base):
    __tablename__ = "AdSet"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AdSetID: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    AdAccountID: Mapped[int] = mapped_column(BigInteger, nullable=False)
    CampaignID: Mapped[int | None] = mapped_column(BigInteger)
    AdSetName: Mapped[str | None] = mapped_column(String(500))
    Status: Mapped[str | None] = mapped_column(String(100))
    ConfiguredStatus: Mapped[str | None] = mapped_column(String(100))
    EffectiveStatus: Mapped[str | None] = mapped_column(String(100))
    OptimizationGoal: Mapped[str | None] = mapped_column(String(100))
    DailyBudget: Mapped[float | None] = mapped_column(Numeric(18, 2))
    LifetimeBudget: Mapped[float | None] = mapped_column(Numeric(18, 2))
    BudgetRemaining: Mapped[float | None] = mapped_column(Numeric(18, 2))
    SpendCap: Mapped[float | None] = mapped_column(Numeric(18, 2))
    SpecialAdCategoryCountry: Mapped[str | None] = mapped_column(String(100))
    IsBudgetScheduleEnabled: Mapped[bool | None] = mapped_column(Boolean)
    IsAdSetBudgetSharingEnabled: Mapped[bool | None] = mapped_column(Boolean)
    DestinationType: Mapped[str | None] = mapped_column(String(100))
    IsDynamicCreative: Mapped[bool | None] = mapped_column(Boolean)
    PacingType: Mapped[str | None] = mapped_column(Text)
    AttributionSpec: Mapped[str | None] = mapped_column(Text)
    PromotedObjectPageID: Mapped[int | None] = mapped_column(BigInteger)
    PromotedObjectPixelID: Mapped[int | None] = mapped_column(BigInteger)
    PromotedObjectAppID: Mapped[int | None] = mapped_column(BigInteger)
    Targeting: Mapped[str | None] = mapped_column(Text)
    TargetingCountries: Mapped[str | None] = mapped_column(Text)
    TargetingAgeMin: Mapped[int | None] = mapped_column(Integer)
    TargetingAgeMax: Mapped[int | None] = mapped_column(Integer)
    TargetingGenders: Mapped[str | None] = mapped_column(Text)
    TargetingPublisherPlatforms: Mapped[str | None] = mapped_column(Text)
    TargetingFacebookPositions: Mapped[str | None] = mapped_column(Text)
    TargetingDevicePlatforms: Mapped[str | None] = mapped_column(Text)
    StartTime: Mapped[datetime | None] = mapped_column(DateTime)
    EndTime: Mapped[datetime | None] = mapped_column(DateTime)
    CreatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    UpdatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    SourceAdSetID: Mapped[int | None] = mapped_column(BigInteger)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Business(Base):
    __tablename__ = "Business"
    __table_args__ = {"schema": STAGING_SCHEMA}
    BusinessID: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    BusinessName: Mapped[str | None] = mapped_column(String(500))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Campaign(Base):
    __tablename__ = "Campaign"
    __table_args__ = {"schema": STAGING_SCHEMA}
    CampaignID: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    AdAccountID: Mapped[str] = mapped_column(String(500), nullable=False)
    CampaignName: Mapped[str | None] = mapped_column(String(500))
    Objective: Mapped[str | None] = mapped_column(String(100))
    BuyingType: Mapped[str | None] = mapped_column(String(100))
    Status: Mapped[str | None] = mapped_column(String(100))
    ConfiguredStatus: Mapped[str | None] = mapped_column(String(100))
    EffectiveStatus: Mapped[str | None] = mapped_column(String(100))
    DailyBudget: Mapped[float | None] = mapped_column(Numeric(18, 2))
    LifetimeBudget: Mapped[float | None] = mapped_column(Numeric(18, 2))
    BudgetRemaining: Mapped[float | None] = mapped_column(Numeric(18, 2))
    SpendCap: Mapped[float | None] = mapped_column(Numeric(18, 2))
    SpecialAdCategories: Mapped[str | None] = mapped_column(Text)
    SpecialAdCategoryCountry: Mapped[str | None] = mapped_column(String(100))
    IsBudgetScheduleEnabled: Mapped[bool | None] = mapped_column(Boolean)
    IsAdSetBudgetSharingEnabled: Mapped[bool | None] = mapped_column(Boolean)
    DestinationType: Mapped[str | None] = mapped_column(String(100))
    IsDynamicCreative: Mapped[bool | None] = mapped_column(Boolean)
    PacingType: Mapped[str | None] = mapped_column(Text)
    AttributionSpec: Mapped[str | None] = mapped_column(Text)
    PromotedObjectPageID: Mapped[int | None] = mapped_column(BigInteger)
    PromotedObjectPixelID: Mapped[int | None] = mapped_column(BigInteger)
    PromotedObjectAppID: Mapped[int | None] = mapped_column(BigInteger)
    StartTime: Mapped[datetime | None] = mapped_column(DateTime)
    StopTime: Mapped[datetime | None] = mapped_column(DateTime)
    CreatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    UpdatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Creative(Base):
    __tablename__ = "Creative"
    __table_args__ = {"schema": STAGING_SCHEMA}
    CreativeId: Mapped[str] = mapped_column(String(100), primary_key=True, autoincrement=False)
    CreativeName: Mapped[str | None] = mapped_column(String(255))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Page(Base):
    __tablename__ = "Page"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PageID: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    PageName: Mapped[str | None] = mapped_column(String(500))
    BusinessID: Mapped[int | None] = mapped_column(BigInteger)
    VerificationStatus: Mapped[str | None] = mapped_column(String(100))
    IsVerified: Mapped[bool | None] = mapped_column(Boolean)
    IsPublished: Mapped[bool | None] = mapped_column(Boolean)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class PageInsightsDaily(Base):
    __tablename__ = "PageInsightsDaily"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PageID: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    DateKey: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    MetricName: Mapped[str] = mapped_column(String(200), primary_key=True, autoincrement=False)
    Date: Mapped[datetime] = mapped_column(Date, nullable=False)
    Value: Mapped[float | None] = mapped_column(Numeric(18, 6))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Post(Base):
    __tablename__ = "Post"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PostID: Mapped[str] = mapped_column(String(100), primary_key=True, autoincrement=False)
    PageID: Mapped[int] = mapped_column(BigInteger, nullable=False)
    CreatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    UpdatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    PermalinkURL: Mapped[str | None] = mapped_column(String(1000))
    StatusType: Mapped[str | None] = mapped_column(String(100))
    IsPublished: Mapped[bool | None] = mapped_column(Boolean)
    IsExpired: Mapped[bool | None] = mapped_column(Boolean)
    IsHidden: Mapped[bool | None] = mapped_column(Boolean)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class PostInsightsDaily(Base):
    __tablename__ = "PostInsightsDaily"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PostID: Mapped[str] = mapped_column(String(100), primary_key=True, autoincrement=False)
    DateKey: Mapped[int] = mapped_column(Integer)
    Date: Mapped[datetime] = mapped_column(Date, nullable=False)
    Shares: Mapped[int | None] = mapped_column(BigInteger)
    Reactions: Mapped[int | None] = mapped_column(BigInteger)
    Comments: Mapped[int | None] = mapped_column(BigInteger)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime, primary_key=True, autoincrement=False)
