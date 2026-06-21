# Changelog

All notable changes to the FMP Data Client project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-23

### Added

#### Core Features (Phases 1-5) - MVP Complete
- **Configuration Management**
  - Environment variable-based configuration with `FMPConfig`
  - Tier-based access control (STARTER, PREMIUM, ULTIMATE)
  - Automatic rate limit calculation based on subscription tier
  - Secure credential masking in config dumps

- **Data Models** (20+ Pydantic v2 models)
  - `DataRequest` with 40+ configuration fields
  - `TickerData` main aggregator model
  - Financial statement models (Income, Balance Sheet, Cash Flow)
  - Valuation models (DCF, Enterprise Value, Key Metrics)
  - Analyst data models (Estimates, Price Targets, Grades)
  - Ownership models (Institutional Holders, Insider Trades)
  - Transcript and SEC filing models
  - News and events models (Dividends, Splits, Earnings)

- **API Fetcher**
  - Async HTTP client with `aiohttp`
  - Token bucket rate limiter (300-3000 calls/min based on tier)
  - Automatic retry with exponential backoff
  - Tier-aware endpoint access validation
  - 40+ specialized type-safe fetch methods
  - Connection pooling and session reuse

- **MySQL Cache Layer** (Optional)
  - Intelligent TTL policies per data type
  - Permanent caching for immutable historical data
  - Short/medium/long TTL for changing data
  - Async operations with connection pooling
  - Graceful degradation without MySQL
  - Cache statistics and management API

- **Core Client Integration**
  - `FMPDataClient` main orchestrator class
  - `get_ticker_data()` comprehensive data fetching
  - Convenience methods: `get_quote()`, `get_profile()`
  - Concurrent fetching with `asyncio.gather()`
  - Automatic cache integration
  - Rate limit management API
  - Async context manager support

#### New Features (Phases 6 & 8)

- **LLM Summarization** (Phase 6)
  - `BaseSummarizer` with Anthropic Claude integration
  - `TranscriptSummarizer` for earnings call analysis
    - Executive summary generation
    - Key metrics extraction
    - Forward guidance parsing
    - Sentiment analysis
    - Q&A highlights extraction
  - `FilingSummarizer` for SEC filing analysis
    - Material changes extraction
    - Risk factor analysis
    - Financial highlights
    - Management commentary parsing
    - Legal matters identification
  - Token usage tracking
  - Configurable models (Haiku/Sonnet/Opus)

- **Command-Line Interface** (Phase 8)
  - `fmp quote` - Get real-time stock quotes
  - `fmp profile` - Company profile information
  - `fmp fundamentals` - Financial statements
  - `fmp analyze` - Comprehensive stock analysis
  - `fmp cache status` - Cache statistics
  - `fmp cache clear` - Clear cached data
  - `fmp config show` - Display configuration
  - `fmp config test` - Test API connection
  - `fmp rate-limit` - Rate limit status
  - Rich terminal output with tables
  - JSON output support

#### Testing Infrastructure (Phase 9 - Partial)
- Comprehensive test suite with pytest
- Mock API response fixtures
- Unit tests for:
  - Configuration and tier validation
  - All data models with validation
  - Rate limiter and fetcher components
  - Client orchestration and caching
- Integration test structure
- pytest configuration with coverage support
- 150+ test cases covering core functionality

#### Documentation & Examples
- `example_basic.py` - Basic usage examples
- `examples/comprehensive_analysis.py` - Advanced analysis examples
- `pytest.ini` - Test configuration
- `CHANGELOG.md` - This file
- Comprehensive inline docstrings
- Type hints throughout codebase

### Technical Details

- **Python Version**: 3.11+
- **Key Dependencies**:
  - `aiohttp` - Async HTTP client
  - `pydantic` v2 - Data validation
  - `anthropic` - Claude API client
  - `tenacity` - Retry logic
  - `mysql-connector-python` - MySQL caching
  - `click` + `rich` - CLI interface
- **Code Statistics**:
  - ~7,000+ lines of production code
  - ~50+ Python modules
  - 150+ test cases
  - 20+ data models
  - 40+ API endpoints

### Architecture

- Async-first design with `asyncio`
- Type-safe operations with Pydantic v2
- Token bucket rate limiting algorithm
- Intelligent caching with per-type TTL policies
- Tier-aware access control
- Modular design with clear separation of concerns

### Known Limitations

- No institutional analysis module yet (Phase 7)
- Test coverage at ~30% (needs expansion)
- Transcript fetching uses simplified quarter calculation
- LLM summarization requires separate Anthropic API key

## [Unreleased]

### Completed Since 0.1.0

#### Phase 10: REST API Server
- FastAPI-based HTTP API with OpenAPI documentation
- API key authentication via MySQL-backed storage
- Per-client rate limiting
- Health check endpoints

#### Phase 11: Docker Deployment
- Multi-stage Dockerfile for containerization
- docker-compose with MySQL service
- Environment variable configuration
- Health check integration

### Planned (Future Versions)

#### Phase 7: Institutional Analysis
- Known holders database (50+ major institutions)
- Weighted holder scoring system
- Active vs passive classification
- Position change significance detection

#### Phase 12: Documentation Enhancement
- API reference documentation
- Architecture deep-dive
- Contributing guidelines
- More example scripts
- Performance benchmarks

---

## Version History

- **0.1.0** (2026-01-23) - Initial release with MVP + LLM + CLI
  - Phases 1-5: Core MVP (Complete)
  - Phase 6: LLM Summarization (Complete)
  - Phase 8: CLI Interface (Complete)
  - Phase 9: Testing (Partial - 30% coverage)
