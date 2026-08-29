"""AI-powered KPI extraction, trend analysis, insights, and semantic search."""

import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np
import openai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.kpi import KPI, KPIHistory, KPIEmbedding
from app.models.file import ExtractedKPI
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class AIService:
    """Provide AI-backed KPI extraction, analysis, and search operations."""

    def __init__(self):
        # Local-first: talk to an OpenAI-compatible server (LM Studio by default).
        # A non-empty key is required by the client even when the server ignores it.
        self.client = openai.OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or "local",
        )
        self.embedding_service = EmbeddingService()

        # Common KPI patterns and keywords
        self.kpi_patterns = {
            "financial": [
                "revenue", "profit", "margin", "cost", "expense", "income", "earnings",
                "cash flow", "roi", "roa", "roce", "ebitda", "ebit", "net income"
            ],
            "operational": [
                "efficiency", "productivity", "throughput", "capacity", "utilization",
                "cycle time", "lead time", "downtime", "uptime", "availability"
            ],
            "customer": [
                "satisfaction", "retention", "acquisition", "lifetime value", "churn",
                "nps", "csat", "response time", "resolution time"
            ],
            "employee": [
                "turnover", "satisfaction", "productivity", "attendance", "training",
                "performance", "engagement", "retention"
            ],
            "marketing": [
                "conversion", "click-through", "impressions", "reach", "engagement",
                "acquisition cost", "lifetime value", "campaign performance"
            ]
        }

    async def extract_kpis_from_text(
        self, text: str, file_id: int, db: AsyncSession
    ) -> List[ExtractedKPI]:
        """Extract KPIs from text using AI and pattern matching."""
        extracted_kpis = []

        # Use OpenAI to identify and extract KPIs
        try:
            prompt = f"""
            Analyze the following text and extract KPIs (Key Performance Indicators).
            For each KPI found, provide:
            1. KPI name (clear, descriptive)
            2. Value (numeric if available)
            3. Unit (if mentioned)
            4. Confidence level (0.0 to 1.0)
            5. Context (surrounding text)

            Text to analyze:
            {text[:4000]}  # Limit text length for API

            Return the results as a JSON array with the following structure:
            [
                {{
                    "kpi_name": "string",
                    "kpi_value": "number or null",
                    "kpi_unit": "string or null",
                    "confidence_score": "number between 0 and 1",
                    "raw_text": "exact text where KPI was found",
                    "context": "surrounding context"
                }}
            ]

            Focus on identifying meaningful business metrics and KPIs.
            """

            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000
            )

            content = response.choices[0].message.content
            try:
                kpis_data = json.loads(content)
                for kpi_data in kpis_data:
                    extracted_kpi = ExtractedKPI(
                        file_id=file_id,
                        kpi_name=kpi_data.get("kpi_name", ""),
                        kpi_value=kpi_data.get("kpi_value"),
                        kpi_unit=kpi_data.get("kpi_unit"),
                        confidence_score=kpi_data.get("confidence_score", 0.5),
                        extraction_method="ai",
                        raw_text=kpi_data.get("raw_text", ""),
                        context=kpi_data.get("context", "")
                    )
                    extracted_kpis.append(extracted_kpi)

            except json.JSONDecodeError:
                # Fallback to pattern matching if AI parsing fails
                extracted_kpis.extend(self._extract_kpis_by_pattern(text, file_id))

        except Exception as err:
            logger.warning("AI extraction failed: %s", err)
            # Fallback to pattern matching
            extracted_kpis.extend(self._extract_kpis_by_pattern(text, file_id))

        return extracted_kpis

    def _extract_kpis_by_pattern(self, text: str, file_id: int) -> List[ExtractedKPI]:
        """Extract KPIs using regex patterns as fallback."""
        extracted_kpis = []

        # Common KPI patterns with regex
        patterns = [
            # Key: Value pattern
            r'(\w+)\s*[:=]\s*([\d,]+\.?\d*)',
            # Value + Unit + KPI type
            r'([\d,]+\.?\d*)\s*([%$€£¥]|\w+)\s*(revenue|profit|margin|cost)',
            # KPI type: Value
            r'(revenue|profit|margin|cost|efficiency|productivity)\s*[:=]\s*([\d,]+\.?\d*)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    kpi_name = match.group(1).strip()
                    value_str = match.group(2).replace(',', '')

                    try:
                        value = float(value_str)
                        extracted_kpi = ExtractedKPI(
                            file_id=file_id,
                            kpi_name=kpi_name,
                            kpi_value=value,
                            kpi_unit=None,
                            confidence_score=0.3,  # Lower confidence for pattern matching
                            extraction_method="regex",
                            raw_text=match.group(0),
                            context=text[max(0, match.start()-50):match.end()+50]
                        )
                        extracted_kpis.append(extracted_kpi)
                    except ValueError:
                        continue

        return extracted_kpis

    async def analyze_kpi_trends(self, kpi_id: int, db: AsyncSession) -> Dict[str, Any]:
        """Analyze KPI trends and provide insights using AI."""
        # Get KPI and its history
        result = await db.execute(select(KPI).where(KPI.id == kpi_id))
        kpi = result.scalar_one_or_none()

        if not kpi:
            return {"error": "KPI not found"}

        # Get historical data
        result = await db.execute(
            select(KPIHistory)
            .where(KPIHistory.kpi_id == kpi_id)
            .order_by(KPIHistory.recorded_at.desc())
            .limit(30)
        )
        history = result.scalars().all()

        if len(history) < 2:
            return {"error": "Insufficient historical data"}

        # Prepare data for analysis
        data_points = []
        for record in reversed(history):  # Chronological order
            data_points.append({
                "date": record.recorded_at.strftime("%Y-%m-%d"),
                "value": float(record.value)
            })

        # Calculate basic statistics
        values = [point["value"] for point in data_points]
        mean_value = np.mean(values)
        std_value = np.std(values)
        if values[-1] > values[0]:
            trend = "increasing"
        elif values[-1] < values[0]:
            trend = "decreasing"
        else:
            trend = "stable"

        # Calculate percentage change
        if values[0] != 0:
            change_percentage = ((values[-1] - values[0]) / values[0]) * 100
        else:
            change_percentage = 0

        # Use AI to generate insights
        try:
            prompt = f"""
            Analyze the following KPI data and provide insights:

            KPI Name: {kpi.name}
            KPI Description: {kpi.description or 'No description'}
            Unit: {kpi.unit or 'No unit specified'}
            Target Value: {kpi.target_value or 'No target specified'}

            Historical Data (last {len(data_points)} data points):
            {json.dumps(data_points, indent=2)}

            Basic Statistics:
            - Mean: {mean_value:.2f}
            - Standard Deviation: {std_value:.2f}
            - Trend: {trend}
            - Change Percentage: {change_percentage:.2f}%

            Please provide:
            1. Trend analysis (what the data shows)
            2. Key insights (3-5 bullet points)
            3. Recommendations (3-5 actionable recommendations)
            4. Anomalies or patterns noticed

            Format the response as JSON:
            {{
                "trend_analysis": "string",
                "insights": ["string", "string", "string"],
                "recommendations": ["string", "string", "string"],
                "anomalies": ["string", "string"],
                "risk_level": "low|medium|high"
            }}
            """

            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000
            )

            content = response.choices[0].message.content
            analysis = json.loads(content)

            return {
                "kpi_id": kpi_id,
                "trend": trend,
                "change_percentage": change_percentage,
                "period": f"{len(data_points)} data points",
                "mean_value": mean_value,
                "std_value": std_value,
                "analysis": analysis,
                "data_points": data_points
            }

        except Exception as err:
            logger.warning("AI trend analysis failed, using fallback: %s", err)
            # Fallback analysis without AI
            return {
                "kpi_id": kpi_id,
                "trend": trend,
                "change_percentage": change_percentage,
                "period": f"{len(data_points)} data points",
                "mean_value": mean_value,
                "std_value": std_value,
                "insights": [
                    f"KPI shows {trend} trend over the analyzed period",
                    f"Change of {change_percentage:.2f}% from first to last measurement",
                    f"Average value: {mean_value:.2f} {kpi.unit or ''}"
                ],
                "recommendations": [
                    "Continue monitoring the trend",
                    "Set up alerts for significant changes",
                    "Review underlying factors affecting the KPI"
                ],
                "data_points": data_points
            }

    async def generate_kpi_recommendations(
        self, organization_id: int, db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Generate AI-powered recommendations for KPIs."""
        # Get all KPIs for the organization
        result = await db.execute(
            select(KPI)
            .where(KPI.organization_id == organization_id)
            .order_by(KPI.updated_at.desc())
        )
        kpis = result.scalars().all()

        if not kpis:
            return []

        # Prepare KPI summary for AI analysis
        kpi_summary = []
        for kpi in kpis:
            # Get latest value
            result = await db.execute(
                select(KPIHistory.value)
                .where(KPIHistory.kpi_id == kpi.id)
                .order_by(KPIHistory.recorded_at.desc())
                .limit(1)
            )
            latest_value = result.scalar_one_or_none()

            kpi_summary.append({
                "name": kpi.name,
                "category": kpi.category.value,
                "current_value": float(latest_value) if latest_value else None,
                "target_value": float(kpi.target_value) if kpi.target_value else None,
                "unit": kpi.unit
            })

        try:
            prompt = f"""
            Analyze the following KPIs for an organization and provide strategic recommendations:

            KPIs:
            {json.dumps(kpi_summary, indent=2)}

            Please provide:
            1. Overall KPI health assessment
            2. Priority areas for improvement
            3. Strategic recommendations (3-5 high-level recommendations)
            4. Missing KPI categories that should be considered

            Format as JSON:
            {{
                "health_assessment": "string",
                "priority_areas": ["string", "string"],
                "strategic_recommendations": ["string", "string", "string"],
                "missing_categories": ["string", "string"],
                "overall_score": "number between 0 and 100"
            }}
            """

            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000
            )

            content = response.choices[0].message.content
            recommendations = json.loads(content)

            return [recommendations]

        except Exception as err:
            logger.warning("AI recommendation generation failed, using fallback: %s", err)
            # Fallback recommendations
            return [{
                "health_assessment": "Unable to perform AI analysis",
                "priority_areas": [
                    "Focus on KPIs with missing targets",
                    "Improve data collection frequency"
                ],
                "strategic_recommendations": [
                    "Set clear targets for all KPIs",
                    "Implement regular KPI reviews",
                    "Establish data quality processes"
                ],
                "missing_categories": [],
                "overall_score": 50
            }]

    async def answer_natural_language_query(
        self, query: str, organization_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """Answer natural language queries about KPIs and data."""
        # Get relevant KPIs and data
        result = await db.execute(
            select(KPI)
            .where(KPI.organization_id == organization_id)
        )
        kpis = result.scalars().all()

        # Prepare context for AI
        kpi_context = []
        for kpi in kpis:
            # Get latest value
            result = await db.execute(
                select(KPIHistory.value)
                .where(KPIHistory.kpi_id == kpi.id)
                .order_by(KPIHistory.recorded_at.desc())
                .limit(1)
            )
            latest_value = result.scalar_one_or_none()

            kpi_context.append({
                "name": kpi.name,
                "category": kpi.category.value,
                "current_value": float(latest_value) if latest_value else None,
                "target_value": float(kpi.target_value) if kpi.target_value else None,
                "unit": kpi.unit,
                "description": kpi.description
            })

        try:
            prompt = f"""
            Answer the following question about the organization's KPIs and data:

            Question: {query}

            Available KPI Data:
            {json.dumps(kpi_context, indent=2)}

            Please provide a comprehensive answer that:
            1. Directly addresses the question
            2. Uses specific data from the KPIs when relevant
            3. Provides insights and context
            4. Suggests follow-up questions if appropriate

            Format the response as JSON:
            {{
                "answer": "detailed answer to the question",
                "data_used": ["list of KPIs or data points referenced"],
                "insights": ["key insights derived"],
                "follow_up_questions": ["suggested follow-up questions"]
            }}
            """

            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4000
            )

            content = response.choices[0].message.content
            answer = json.loads(content)

            return answer

        except Exception as e:
            return {
                "answer": f"I'm unable to process your query at the moment. Error: {str(e)}",
                "data_used": [],
                "insights": [],
                "follow_up_questions": []
            }

    async def generate_comprehensive_report(
        self, kpis, dashboards, report_type: str = "executive",
        include_recommendations: bool = True,
    ) -> Dict[str, Any]:
        """Generate an AI-powered narrative report from KPIs and dashboards.

        kpis and dashboards are ORM objects already loaded by the caller. Returns a
        report dict; on any failure returns a structured fallback instead of raising.
        """
        kpi_summary = [
            {
                "name": kpi.name,
                "category": kpi.category.value if kpi.category else None,
                "current_value": float(kpi.current_value) if kpi.current_value else None,
                "target_value": float(kpi.target_value) if kpi.target_value else None,
                "unit": kpi.unit,
            }
            for kpi in kpis
        ]
        dashboard_names = [getattr(d, "name", None) for d in dashboards]
        rec_line = "Include 3-5 strategic recommendations." if include_recommendations \
            else "Do not include recommendations."

        try:
            prompt = f"""
            Produce a {report_type} report for an organization based on this data.
            {rec_line}

            KPIs:
            {json.dumps(kpi_summary, indent=2)}

            Dashboards: {json.dumps(dashboard_names)}

            Format the response as JSON:
            {{
                "title": "report title",
                "summary": "executive summary",
                "highlights": ["key highlight", "..."],
                "concerns": ["area of concern", "..."],
                "recommendations": ["recommendation", "..."]
            }}
            """

            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
            )
            return json.loads(response.choices[0].message.content)

        except Exception as err:
            logger.warning("Report generation failed: %s", err)
            return {
                "title": f"{report_type.title()} Report",
                "summary": f"Unable to generate the report at this time. Error: {err}",
                "highlights": [],
                "concerns": [],
                "recommendations": [],
            }

    async def create_kpi_embedding(self, kpi: KPI, db: AsyncSession) -> Optional[KPIEmbedding]:
        """Create vector embedding for a KPI to enable semantic search and AI analysis."""
        try:
            # Prepare text for embedding
            kpi_text_parts = [
                f"KPI Name: {kpi.name}",
                f"Description: {kpi.description or 'No description'}",
                f"Category: {kpi.category.value if kpi.category else 'other'}",
                f"Unit: {kpi.unit or 'No unit'}",
            ]

            # Add calculation method if available
            if kpi.calculation_method:
                kpi_text_parts.append(f"Calculation: {kpi.calculation_method}")

            # Add data source if available
            if kpi.data_source:
                kpi_text_parts.append(f"Data Source: {kpi.data_source}")

            # Add frequency if available
            if kpi.frequency:
                kpi_text_parts.append(f"Update Frequency: {kpi.frequency}")

            # Add target and current values
            if kpi.target_value:
                kpi_text_parts.append(f"Target Value: {kpi.target_value}")
            if kpi.current_value:
                kpi_text_parts.append(f"Current Value: {kpi.current_value}")

            # Combine all text
            kpi_text = " | ".join(kpi_text_parts)

            # Generate embedding using OpenAI
            embedding_response = self.client.embeddings.create(
                model=settings.LLM_EMBEDDING_MODEL,
                input=kpi_text
            )

            embedding_vector = embedding_response.data[0].embedding

            # Create KPI embedding record
            kpi_embedding = KPIEmbedding(
                kpi_id=kpi.id,
                embedding=embedding_vector,
                content=kpi_text,
                chunk_metadata={
                    "kpi_name": kpi.name,
                    "category": kpi.category.value if kpi.category else None,
                    "unit": kpi.unit,
                    "frequency": kpi.frequency,
                    "has_target": bool(kpi.target_value),
                    "has_current_value": bool(kpi.current_value),
                    "created_at": datetime.now().isoformat()
                }
            )

            db.add(kpi_embedding)
            await db.commit()
            await db.refresh(kpi_embedding)

            return kpi_embedding

        except Exception as err:
            logger.error("Error creating KPI embedding: %s", err)
            return None

    async def search_similar_kpis(
        self, query: str, db: AsyncSession, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for KPIs similar to the given query using vector similarity."""
        try:
            # Generate embedding for the search query
            embedding_response = self.client.embeddings.create(
                model=settings.LLM_EMBEDDING_MODEL,
                input=query
            )

            query_embedding = embedding_response.data[0].embedding

            # Use the embedding service to find similar KPIs
            similar_kpis = await self.embedding_service.search_similar_kpis(
                query_embedding,
                db,
                limit=limit
            )

            return similar_kpis

        except Exception as err:
            logger.error("Error searching similar KPIs: %s", err)
            return []

    async def generate_kpi_insights(self, kpi: KPI, db: AsyncSession) -> Dict[str, Any]:
        """Generate AI-powered insights for a specific KPI."""
        try:
            # Get recent history for the KPI
            history_result = await db.execute(
                select(KPIHistory)
                .where(KPIHistory.kpi_id == kpi.id)
                .order_by(KPIHistory.recorded_at.desc())
                .limit(10)
            )
            history = history_result.scalars().all()

            # Prepare context for AI analysis
            context = {
                "kpi_name": kpi.name,
                "description": kpi.description,
                "category": kpi.category.value if kpi.category else "other",
                "unit": kpi.unit,
                "target_value": float(kpi.target_value) if kpi.target_value else None,
                "current_value": float(kpi.current_value) if kpi.current_value else None,
                "frequency": kpi.frequency,
                "recent_values": [
                    {
                        "value": float(h.value),
                        "date": h.recorded_at.isoformat(),
                        "notes": h.notes
                    } for h in history
                ]
            }

            prompt = f"""
            Analyze the following KPI and provide insights:

            KPI Details: {json.dumps(context, indent=2)}

            Please provide:
            1. Performance analysis (vs target, trends)
            2. Key insights and patterns
            3. Recommendations for improvement
            4. Potential risks or opportunities
            5. Suggested actions

            Return your response as a JSON object with the following structure:
            {{
                "performance_status": "excellent|good|warning|critical",
                "trend": "improving|stable|declining",
                "key_insights": ["insight 1", "insight 2", ...],
                "recommendations": ["recommendation 1", "recommendation 2", ...],
                "risks": ["risk 1", "risk 2", ...],
                "opportunities": ["opportunity 1", "opportunity 2", ...],
                "suggested_actions": ["action 1", "action 2", ...],
                "confidence_score": 0.85
            }}
            """

            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4000
            )

            content = response.choices[0].message.content
            insights = json.loads(content)

            return insights

        except Exception as e:
            return {
                "performance_status": "unknown",
                "trend": "unknown",
                "key_insights": [f"Unable to analyze KPI: {str(e)}"],
                "recommendations": [],
                "risks": [],
                "opportunities": [],
                "suggested_actions": [],
                "confidence_score": 0.0
            }
