-- Migration to enhance KPI table with additional fields for KPI Builder
-- Run this migration to add new columns to the existing kpis table

-- Add enhanced fields to kpis table
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS calculation_method TEXT;
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS frequency VARCHAR(50);
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS data_source VARCHAR(255);
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS threshold_warning DECIMAL(15, 2);
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS threshold_critical DECIMAL(15, 2);
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE kpis ADD COLUMN IF NOT EXISTS kpi_metadata JSONB;

-- Create index on is_active for faster filtering
CREATE INDEX IF NOT EXISTS idx_kpis_is_active ON kpis(is_active);

-- Create index on frequency for analytics
CREATE INDEX IF NOT EXISTS idx_kpis_frequency ON kpis(frequency);

-- Create index on category for filtering
CREATE INDEX IF NOT EXISTS idx_kpis_category ON kpis(category);

-- Update existing records to have is_active = true
UPDATE kpis SET is_active = true WHERE is_active IS NULL;