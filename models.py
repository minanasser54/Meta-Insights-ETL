from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


STAGING_SCHEMA = "STG.Marketing"


class Base(DeclarativeBase):
    pass


class Ad(Base):
    __tablename__ = "Ad"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AdID: Mapped[str] = mapped_column(String(50), primary_key=True)
    AdAccountID: Mapped[str | None] = mapped_column(String(50))
    CampaignID: Mapped[str | None] = mapped_column(String(50))
    AdSetID: Mapped[str | None] = mapped_column(String(50))
    CreativeID: Mapped[str | None] = mapped_column(String(50))
    AdName: Mapped[str | None] = mapped_column(String(255))
    Status: Mapped[str | None] = mapped_column(String(50))
    ConfiguredStatus: Mapped[str | None] = mapped_column(String(50))
    EffectiveStatus: Mapped[str | None] = mapped_column(String(50))
    AdActiveTime: Mapped[datetime | None] = mapped_column(DateTime)
    SourceAdID: Mapped[str | None] = mapped_column(String(50))
    EffectiveObjectStoryID: Mapped[str | None] = mapped_column(String(100))
    ObjectStoryID: Mapped[str | None] = mapped_column(String(100))
    ScheduledStartTime: Mapped[datetime | None] = mapped_column(DateTime)
    ScheduledEndTime: Mapped[datetime | None] = mapped_column(DateTime)
    CreatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    UpdatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class AdAccount(Base):
    __tablename__ = "AdAccount"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AccountID: Mapped[str] = mapped_column(String(50), primary_key=True)
    AccountName: Mapped[str | None] = mapped_column(String(255))
    AccountStatus: Mapped[int | None] = mapped_column(Integer)
    DisableReason: Mapped[int | None] = mapped_column(Integer)
    Currency: Mapped[str | None] = mapped_column(String(10))
    TimezoneName: Mapped[str | None] = mapped_column(String(100))
    TimezoneOffsetHrsUtc: Mapped[float | None] = mapped_column(Float)
    AmountSpent: Mapped[str | None] = mapped_column(String(50))
    Balance: Mapped[str | None] = mapped_column(String(50))
    SpendCap: Mapped[str | None] = mapped_column(String(50))
    MinCampaignGroupSpendCap: Mapped[str | None] = mapped_column(String(50))
    MinDailyBudget: Mapped[str | None] = mapped_column(String(50))
    IsPersonal: Mapped[bool | None] = mapped_column(Boolean)
    BusinessID: Mapped[str | None] = mapped_column(String(50))
    FundingSourceID: Mapped[str | None] = mapped_column(String(50))
    FundingSourceDisplayString: Mapped[str | None] = mapped_column(String(255))
    FundingSourceType: Mapped[int | None] = mapped_column(Integer)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class AdInsightsDaily(Base):
    __tablename__ = "AdInsightsDaily"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AdID: Mapped[str] = mapped_column(String(50), primary_key=True)
    Date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    AdSetID: Mapped[str | None] = mapped_column(String(50))
    CampaignID: Mapped[str | None] = mapped_column(String(50))
    AdAccountID: Mapped[str | None] = mapped_column(String(50))
    DateKey: Mapped[int | None] = mapped_column(Integer)
    Impressions: Mapped[float | None] = mapped_column(Float)
    Reach: Mapped[float | None] = mapped_column(Float)
    Frequency: Mapped[float | None] = mapped_column(Float)
    Spend: Mapped[float | None] = mapped_column(Float)
    SocialSpend: Mapped[float | None] = mapped_column(Float)
    Clicks: Mapped[float | None] = mapped_column(Float)
    UniqueClicks: Mapped[float | None] = mapped_column(Float)
    CPC: Mapped[float | None] = mapped_column(Float)
    CPP: Mapped[float | None] = mapped_column(Float)
    InlineLinkClicks: Mapped[float | None] = mapped_column(Float)
    InlineLinkClickCTR: Mapped[float | None] = mapped_column(Float)
    CostPerInlineLinkClick: Mapped[float | None] = mapped_column(Float)
    InlinePostEngagement: Mapped[float | None] = mapped_column(Float)
    CostPerInlinePostEngagement: Mapped[float | None] = mapped_column(Float)
    Leads: Mapped[float | None] = mapped_column(Float)
    CostPerLead: Mapped[float | None] = mapped_column(Float)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class AdSet(Base):
    __tablename__ = "AdSet"
    __table_args__ = {"schema": STAGING_SCHEMA}
    AdSetID: Mapped[str] = mapped_column(String(50), primary_key=True)
    AdAccountID: Mapped[str | None] = mapped_column(String(50))
    CampaignID: Mapped[str | None] = mapped_column(String(50))
    AdSetName: Mapped[str | None] = mapped_column(String(255))
    Status: Mapped[str | None] = mapped_column(String(50))
    ConfiguredStatus: Mapped[str | None] = mapped_column(String(50))
    EffectiveStatus: Mapped[str | None] = mapped_column(String(50))
    OptimizationGoal: Mapped[str | None] = mapped_column(String(100))
    DailyBudget: Mapped[float | None] = mapped_column(Float)
    LifetimeBudget: Mapped[float | None] = mapped_column(Float)
    BudgetRemaining: Mapped[float | None] = mapped_column(Float)
    SpendCap: Mapped[float | None] = mapped_column(Float)
    SpecialAdCategoryCountry: Mapped[str | None] = mapped_column(String(20))
    IsBudgetScheduleEnabled: Mapped[bool | None] = mapped_column(Boolean)
    IsAdSetBudgetSharingEnabled: Mapped[bool | None] = mapped_column(Boolean)
    DestinationType: Mapped[str | None] = mapped_column(String(100))
    IsDynamicCreative: Mapped[bool | None] = mapped_column(Boolean)
    PacingType: Mapped[str | None] = mapped_column(String(100))
    AttributionSpec: Mapped[str | None] = mapped_column(Text)
    PromotedObjectPageID: Mapped[str | None] = mapped_column(String(50))
    PromotedObjectPixelID: Mapped[str | None] = mapped_column(String(50))
    PromotedObjectAppID: Mapped[str | None] = mapped_column(String(50))
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
    SourceAdSetID: Mapped[str | None] = mapped_column(String(50))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Business(Base):
    __tablename__ = "Business"
    __table_args__ = {"schema": STAGING_SCHEMA}
    BusinessID: Mapped[str] = mapped_column(String(50), primary_key=True)
    BusinessName: Mapped[str | None] = mapped_column(String(255))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Campaign(Base):
    __tablename__ = "Campaign"
    __table_args__ = {"schema": STAGING_SCHEMA}
    CampaignID: Mapped[str] = mapped_column(String(50), primary_key=True)
    AdAccountID: Mapped[str | None] = mapped_column(String(50))
    CampaignName: Mapped[str | None] = mapped_column(String(255))
    Objective: Mapped[str | None] = mapped_column(String(100))
    BuyingType: Mapped[str | None] = mapped_column(String(100))
    Status: Mapped[str | None] = mapped_column(String(50))
    ConfiguredStatus: Mapped[str | None] = mapped_column(String(50))
    EffectiveStatus: Mapped[str | None] = mapped_column(String(50))
    DailyBudget: Mapped[float | None] = mapped_column(Float)
    LifetimeBudget: Mapped[float | None] = mapped_column(Float)
    BudgetRemaining: Mapped[float | None] = mapped_column(Float)
    SpendCap: Mapped[float | None] = mapped_column(Float)
    SpecialAdCategories: Mapped[str | None] = mapped_column(Text)
    SpecialAdCategoryCountry: Mapped[str | None] = mapped_column(String(20))
    IsBudgetScheduleEnabled: Mapped[bool | None] = mapped_column(Boolean)
    IsAdSetBudgetSharingEnabled: Mapped[bool | None] = mapped_column(Boolean)
    DestinationType: Mapped[str | None] = mapped_column(String(100))
    IsDynamicCreative: Mapped[bool | None] = mapped_column(Boolean)
    PacingType: Mapped[str | None] = mapped_column(String(100))
    AttributionSpec: Mapped[str | None] = mapped_column(Text)
    PromotedObjectPageID: Mapped[str | None] = mapped_column(String(50))
    PromotedObjectPixelID: Mapped[str | None] = mapped_column(String(50))
    PromotedObjectAppID: Mapped[str | None] = mapped_column(String(50))
    StartTime: Mapped[datetime | None] = mapped_column(DateTime)
    StopTime: Mapped[datetime | None] = mapped_column(DateTime)
    CreatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    UpdatedTime: Mapped[datetime | None] = mapped_column(DateTime)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Creative(Base):
    __tablename__ = "Creative"
    __table_args__ = {"schema": STAGING_SCHEMA}
    CreativeId: Mapped[str] = mapped_column(String(50), primary_key=True)
    CreativeName: Mapped[str | None] = mapped_column(String(255))
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Page(Base):
    __tablename__ = "Page"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PageID: Mapped[str] = mapped_column(String(50), primary_key=True)
    PageName: Mapped[str | None] = mapped_column(String(255))
    BusinessID: Mapped[str | None] = mapped_column(String(50))
    VerificationStatus: Mapped[str | None] = mapped_column(String(100))
    IsVerified: Mapped[bool | None] = mapped_column(Boolean)
    IsPublished: Mapped[bool | None] = mapped_column(Boolean)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class PageInsightsDaily(Base):
    __tablename__ = "PageInsightsDaily"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PageID: Mapped[str] = mapped_column(String(50), primary_key=True)
    Date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    DateKey: Mapped[int | None] = mapped_column(Integer)
    MetricName: Mapped[str] = mapped_column(String(100), primary_key=True)
    Value: Mapped[float | None] = mapped_column(Float)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)


class Post(Base):
    __tablename__ = "Post"
    __table_args__ = {"schema": STAGING_SCHEMA}
    PostID: Mapped[str] = mapped_column(String(50), primary_key=True)
    PageID: Mapped[str | None] = mapped_column(String(50))
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
    PostID: Mapped[str] = mapped_column(String(50), primary_key=True)
    Date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    Shares: Mapped[float | None] = mapped_column(Float)
    Reactions: Mapped[float | None] = mapped_column(Float)
    Comments: Mapped[float | None] = mapped_column(Float)
    LoadDate: Mapped[datetime | None] = mapped_column(DateTime)