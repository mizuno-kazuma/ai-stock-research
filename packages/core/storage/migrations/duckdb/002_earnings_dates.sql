CREATE TABLE IF NOT EXISTS earnings_dates (
    ticker VARCHAR NOT NULL,
    market VARCHAR NOT NULL,
    announce_date DATE NOT NULL,
    fiscal_period VARCHAR,
    source VARCHAR,
    ingested_at TIMESTAMP,
    PRIMARY KEY (ticker, market, announce_date)
);
