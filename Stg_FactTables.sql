
-- Ad Insights Daily
CREATE TABLE [STG.Marketing].[AdInsightsDaily]
(
    AdID                            BIGINT          NOT NULL,
    AdSetID                         BIGINT          NULL,
    CampaignID                      BIGINT          NULL,
    AdAccountID                     BIGINT          NOT NULL,

    Date                            DATE            NOT NULL,
    DateKey                         INT             NOT NULL,

    Impressions                    BIGINT          NULL,
    Reach                           BIGINT          NULL,
    Frequency                      DECIMAL(18,6)   NULL,

    Spend                          DECIMAL(18,2)   NULL,
    SocialSpend                    DECIMAL(18,2)   NULL,

    Clicks                         BIGINT          NULL,
    UniqueClicks                   BIGINT          NULL,

    CPC                             DECIMAL(18,6)   NULL,
    CPP                             DECIMAL(18,6)   NULL,

    InlineLinkClicks               BIGINT          NULL,
    InlineLinkClickCTR             DECIMAL(18,6)   NULL,
    CostPerInlineLinkClick         DECIMAL(18,6)   NULL,

    InlinePostEngagement            BIGINT          NULL,
    CostPerInlinePostEngagement     DECIMAL(18,6)   NULL,

    -- NEW
    Leads                           BIGINT          NULL,
    CostPerLead                     DECIMAL(18,6)   NULL,

    LoadDate                        DATETIME2(0)    NOT NULL DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_AdInsightsDaily
        PRIMARY KEY (AdID, DateKey)
);
GO

select top 10 * from [STG.Marketing].[AdInsightsDaily]

select count(*) from [STG.Marketing].[AdInsightsDaily] -- 26,924

select distinct(AdAccountID) from [STG.Marketing].[AdInsightsDaily]

-- Post Insights Daily
CREATE TABLE [STG.Marketing].[PostInsightsDaily]
(
    PostID              NVARCHAR(100)   NOT NULL,
    Date                DATE            NOT NULL,
    DateKey             INT             NOT NULL,

    Shares              BIGINT          NULL,
    Reactions           BIGINT          NULL,
    Comments            BIGINT          NULL,

    LoadDate            DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_PostInsightsDaily
        PRIMARY KEY (PostID, DateKey)
);
GO


-- Page Insights Daily
CREATE TABLE [STG.Marketing].[PageInsightsDaily]
(
    PageID                  BIGINT          NOT NULL,
    Date                    DATE            NOT NULL,
    DateKey                 INT             NOT NULL,

    MetricName              NVARCHAR(200)   NOT NULL,
    Value                   DECIMAL(18,6)   NULL,

    LoadDate                DATETIME2(0)    NOT NULL
        DEFAULT GETDATE(),

    CONSTRAINT PK_STG_Marketing_PageInsightsDaily
        PRIMARY KEY (PageID, DateKey, MetricName)
);
GO
