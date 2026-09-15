-- CREATE SCHEMA [STG.Marketing]

-- Business
CREATE TABLE [STG.Marketing].[Business]
(
    BusinessID      BIGINT          ,
    BusinessName    NVARCHAR(500)   NULL,
    LoadDate        DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

     CONSTRAINT PK_STG_Marketing_Business
        PRIMARY KEY (BusinessID)
);
GO

Select * from [STG.Marketing].[Business]


-- AdAccount
CREATE TABLE [STG.Marketing].[AdAccount]
(
    AccountID                   NVARCHAR(500)   NOT NULL,
    AccountName                 NVARCHAR(500)   NULL,

    AccountStatus               INT             NULL,
    DisableReason               INT             NULL,

    Currency                    NVARCHAR(50)    NULL,

    TimezoneName                NVARCHAR(200)   NULL,
    TimezoneOffsetHrsUtc        DECIMAL(5,2)    NULL,

    AmountSpent                 DECIMAL(18,2)   NULL,
    Balance                     DECIMAL(18,2)   NULL,
    SpendCap                    DECIMAL(18,2)   NULL,
    MinCampaignGroupSpendCap    DECIMAL(18,2)   NULL,
    MinDailyBudget              DECIMAL(18,2)   NULL,

    IsPersonal                  BIT             NULL,

    BusinessID                  BIGINT          NULL,

    FundingSourceID             BIGINT          NULL,
    FundingSourceDisplayString  NVARCHAR(500)   NULL,
    FundingSourceType           INT             NULL,

    LoadDate                    DATETIME2(0)    NOT NULL
        CONSTRAINT DF_STG_Marketing_AdAccount_LoadDate
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_AdAccount
        PRIMARY KEY (AccountID)
);
GO

select * from [STG.Marketing].[AdAccount]

-- Page
CREATE TABLE [STG.Marketing].[Page]
(
    PageID                  BIGINT          NOT NULL,
    PageName                NVARCHAR(500)   NULL,
    BusinessID              BIGINT          NULL,

    VerificationStatus      NVARCHAR(100)   NULL,
    IsVerified              BIT             NULL,
    IsPublished              BIT             NULL,

    LoadDate                DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_Page
        PRIMARY KEY (PageID)
);
GO

select * from [STG.Marketing].[Page]

-- Campaign
CREATE TABLE [STG.Marketing].[Campaign]
(
    CampaignID                      BIGINT          NOT NULL,
    AdAccountID                     NVARCHAR(500)   NOT NULL,

    CampaignName                    NVARCHAR(500)   NULL,
    Objective                       NVARCHAR(100)   NULL,
    BuyingType                      NVARCHAR(100)   NULL,

    Status                          NVARCHAR(100)   NULL,
    ConfiguredStatus                NVARCHAR(100)   NULL,
    EffectiveStatus                 NVARCHAR(100)   NULL,

    DailyBudget                     DECIMAL(18,2)   NULL,
    LifetimeBudget                  DECIMAL(18,2)   NULL,
    BudgetRemaining                 DECIMAL(18,2)   NULL,
    SpendCap                        DECIMAL(18,2)   NULL,

    SpecialAdCategories             NVARCHAR(MAX)   NULL,
    SpecialAdCategoryCountry        NVARCHAR(100)   NULL,

    IsBudgetScheduleEnabled         BIT             NULL,
    IsAdSetBudgetSharingEnabled     BIT             NULL,

    DestinationType                 NVARCHAR(100)   NULL,
    IsDynamicCreative               BIT             NULL,

    PacingType                      NVARCHAR(MAX)   NULL,
    AttributionSpec                 NVARCHAR(MAX)   NULL,

    PromotedObjectPageID            BIGINT          NULL,
    PromotedObjectPixelID           BIGINT          NULL,
    PromotedObjectAppID             BIGINT          NULL,

    StartTime                       DATETIME2(0)    NULL,
    StopTime                        DATETIME2(0)    NULL,
    CreatedTime                     DATETIME2(0)    NULL,
    UpdatedTime                     DATETIME2(0)    NULL,

    LoadDate                        DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_Campaign
        PRIMARY KEY (CampaignID)
);
GO

select * from [STG.Marketing].[Campaign] --2,493

-- AdSet
CREATE TABLE [STG.Marketing].[AdSet]
(
    AdSetID                         BIGINT          NOT NULL,
    AdAccountID                     BIGINT          NOT NULL,
    CampaignID                      BIGINT          NULL,

    AdSetName                       NVARCHAR(500)   NULL,

    Status                          NVARCHAR(100)   NULL,
    ConfiguredStatus                NVARCHAR(100)   NULL,
    EffectiveStatus                 NVARCHAR(100)   NULL,

    OptimizationGoal               NVARCHAR(100)   NULL,

    DailyBudget                     DECIMAL(18,2)   NULL,
    LifetimeBudget                  DECIMAL(18,2)   NULL,
    BudgetRemaining                 DECIMAL(18,2)   NULL,
    SpendCap                        DECIMAL(18,2)   NULL,

    SpecialAdCategoryCountry        NVARCHAR(100)   NULL,

    IsBudgetScheduleEnabled         BIT             NULL,
    IsAdSetBudgetSharingEnabled     BIT             NULL,
    DestinationType                 NVARCHAR(100)   NULL,
    IsDynamicCreative               BIT             NULL,

    PacingType                      NVARCHAR(MAX)   NULL,
    AttributionSpec                 NVARCHAR(MAX)   NULL,

    PromotedObjectPageID            BIGINT          NULL,
    PromotedObjectPixelID           BIGINT          NULL,
    PromotedObjectAppID             BIGINT          NULL,

    Targeting                       NVARCHAR(MAX)   NULL,
    TargetingCountries              NVARCHAR(MAX)   NULL,

    TargetingAgeMin                 INT             NULL,
    TargetingAgeMax                 INT             NULL,

    TargetingGenders                NVARCHAR(MAX)   NULL,
    TargetingPublisherPlatforms     NVARCHAR(MAX)   NULL,
    TargetingFacebookPositions      NVARCHAR(MAX)   NULL,
    TargetingDevicePlatforms        NVARCHAR(MAX)   NULL,

    StartTime                       DATETIME2(0)    NULL,
    EndTime                         DATETIME2(0)    NULL,
    CreatedTime                     DATETIME2(0)    NULL,
    UpdatedTime                     DATETIME2(0)    NULL,

    SourceAdSetID                   BIGINT          NULL,

    LoadDate                        DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_AdSet
        PRIMARY KEY (AdSetID)
);
GO
select * from [STG.Marketing].[AdSet]
select distinct(adaccountid) from [STG.Marketing].[AdSet]

SELECT DISTINCT
    TRY_CONVERT(BIGINT, a.AccountID) AS AccountID
FROM [STG.Marketing].[AdAccount] a

EXCEPT

SELECT DISTINCT
    s.AdAccountID
FROM [STG.Marketing].[AdSet] s;


SELECT
    COUNT(*) AS TotalRows,
    COUNT(DISTINCT AccountID) AS DistinctAccounts,
    COUNT(DISTINCT TRY_CONVERT(BIGINT, AccountID)) AS DistinctNumericAccounts
FROM [STG.Marketing].[AdAccount];

SELECT DISTINCT
    a.AccountID
FROM [STG.Marketing].[AdAccount] a
WHERE NOT EXISTS (
    SELECT 1
    FROM [STG.Marketing].[AdSet] s
    WHERE s.AdAccountID =
          TRY_CONVERT(BIGINT, REPLACE(a.AccountID, 'act_', ''))
);


-- Ad
CREATE TABLE [STG.Marketing].[Ad]
(
    AdID                        BIGINT          NOT NULL,
    AdAccountID                BIGINT          NOT NULL,
    CampaignID                 BIGINT          NULL,
    AdSetID                    BIGINT          NULL,
    CreativeID                 BIGINT          NULL,

    AdName                     NVARCHAR(500)   NULL,

    Status                     NVARCHAR(100)   NULL,
    ConfiguredStatus           NVARCHAR(100)   NULL,
    EffectiveStatus            NVARCHAR(100)   NULL,

    AdActiveTime               INT             NULL,

    SourceAdID                 BIGINT          NULL,

    EffectiveObjectStoryID     NVARCHAR(500)   NULL,
    ObjectStoryID              NVARCHAR(500)   NULL,

    ScheduledStartTime         DATETIME2(0)    NULL,
    ScheduledEndTime           DATETIME2(0)    NULL,

    CreatedTime                DATETIME2(0)    NULL,
    UpdatedTime                DATETIME2(0)    NULL,

    LoadDate                   DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_Ad
        PRIMARY KEY (AdID)
);
GO

select * from [STG.Marketing].[Ad] -- 16,116

select * from [STG.Marketing].[Ad]
where AdSetID is null

select distinct(adaccountid) from [STG.Marketing].[Ad]


-- Post
CREATE TABLE [STG.Marketing].[Post]
(
    PostID                  NVARCHAR(100)   NOT NULL,
    PageID                  BIGINT          NOT NULL,

    CreatedTime             DATETIME2(0)    NULL,
    UpdatedTime             DATETIME2(0)    NULL,

    PermalinkURL            NVARCHAR(1000)  NULL,

    StatusType              NVARCHAR(100)   NULL,

    IsPublished             BIT             NULL,
    IsExpired               BIT             NULL,
    IsHidden                BIT             NULL,

    LoadDate                DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_Post
        PRIMARY KEY (PostID)
);
GO

select * from [STG.Marketing].[Post] -- 27,866
select distinct(pageid) from [STG.Marketing].[Post]


CREATE TABLE [STG.Marketing].[Creative] (
    CreativeId      NVARCHAR(100) NOT NULL,
    CreativeName    NVARCHAR(255) NULL,

    AdAccountId     NVARCHAR(100) NULL,

    CreativeType    NVARCHAR(50)  NULL,  -- IMAGE / VIDEO / MIXED / UNKNOWN

    ImageHash       NVARCHAR(255) NULL,
    VideoId         NVARCHAR(100) NULL,

    LoadDate        DATETIME2(0) NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_Creative
        PRIMARY KEY (CreativeId)
);
GO

select count(*) from [STG.Marketing].[Creative] -- 4,904
select * from [STG.Marketing].[Creative] -- 4,904


SELECT TOP 30
    RunId,
    FunctionName,
    RunStartedAt,
    RunFinishedAt,
    Status,
    RowsReceived,
    RowsWritten,
    ErrorCount,
    ErrorMessage
FROM [DataWarehouse].[dbo.Marketing].[etl_function_runs]
ORDER BY RunId DESC;

SELECT a.AccountID
FROM [STG.Marketing].[AdAccount] a
WHERE TRY_CONVERT(BIGINT, a.AccountID) IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM [STG.Marketing].[AdSet] s
      WHERE s.AdAccountID = TRY_CONVERT(BIGINT, a.AccountID)
  );