# Incipit Genie Pro

A sophisticated citation processing tool for academic documents that converts endnotes to page-referenced format with contextual incipits, supporting multiple academic citation styles.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/deploy)

## Features

- **Smart Incipit Extraction**: Automatically extracts contextual phrases from sentences containing citations
- **Multi-Style Support**: Formats citations according to 8 major academic styles (Chicago, Turabian, Bluebook, AMA, Oxford, OSCOLA, MHRA, Vancouver)
- **Preview Mode**: Audit changes before processing
- **Enhanced Parsers**: Support for 'Et al.', arbitration documents, personal archives
- **CMS 17th Edition**: Ibid support, short notes, author reordering
- **Journal Database**: 20+ psychiatric and medical journal abbreviations
- **Page Reference Integration**: Creates bookmarks and page references for easy navigation

## Quick Deploy to Railway

### One-Click Deploy

1. Click the "Deploy on Railway" button above
2. Sign in to Railway (or create account)
3. Railway will automatically:
   - Fork this repository
   - Set up the environment
   - Deploy the application
4. Once deployed, visit your app URL

### Manual Deploy to Railway

1. **Fork or Clone this Repository**
```bash
git clone https://github.com/yourusername/incipit-genie-pro.git
cd incipit-genie-pro
```

2. **Install Railway CLI** (optional)
```bash
npm install -g @railway/cli
```

3. **Login to Railway**
```bash
railway login
```

4. **Initialize Project**
```bash
railway init
```

5. **Deploy**
```bash
railway up
```

6. **Set Environment Variables** (in Railway Dashboard)
- Go to your project dashboard
- Navigate to Variables tab
- Add:
  - `SECRET_KEY`: Generate a secure random key
  - `FLASK_ENV`: Set to `production`
  - `PORT`: Railway sets this automatically

## Local Development

### Prerequisites
- Python 3.8+
- pip package manager

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/incipit-genie-pro.git
cd incipit-genie-pro
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Create templates directory**
```bash
mkdir -p templates
mv index.html templates/
```

5. **Set environment variables** (optional)
```bash
cp .env.example .env
# Edit .env with your settings
```

6. **Run the application**
```bash
python citationparserapp.py
```

Visit `http://localhost:5000`

## File Structure

```
incipit-genie-pro/
├── citationparserapp.py    # Main Flask application
├── templates/
│   └── index.html          # Web interface
├── requirements.txt        # Python dependencies
├── runtime.txt            # Python version for Railway
├── Procfile              # Railway process configuration
├── railway.json          # Railway deployment config
├── .env.example          # Environment variables template
├── .gitignore           # Git ignore rules
├── LICENSE              # MIT License
└── README.md            # This file
```

## Usage

1. **Upload Document**: Select a .docx file with endnotes
2. **Configure Options**:
   - Incipit Length: 1-10 words (default: 3)
   - Format: Bold or Italic
   - Citation Style: Choose from 8 academic styles
   - Preview Mode: Check changes before processing
3. **Process**: Click "Process Document"
4. **Download**: Save the converted file

## Citation Styles

### US Styles
- **Chicago**: Author name swapping, parenthetical publication data
- **Turabian**: Similar to Chicago with minor variations
- **Bluebook**: Legal citation format (conservative changes)
- **AMA**: Medical format with semicolon separators

### UK Styles
- **Oxford**: Similar to Chicago but UK conventions
- **OSCOLA**: Legal citation (minimal changes)
- **MHRA**: Author swapping without parentheses
- **Vancouver**: Medical format, numbered references

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | Auto-generated |
| `FLASK_ENV` | Environment (development/production) | production |
| `PORT` | Server port | 5000 |
| `MAX_CONTENT_LENGTH` | Max upload size in bytes | 104857600 (100MB) |
| `RAILWAY_ENVIRONMENT` | Set by Railway automatically | - |

### Railway-Specific Settings

The app automatically detects Railway deployment and:
- Uses system temp directory for file storage
- Enables proxy headers support
- Sets production logging
- Implements automatic cleanup of old files

## Security Features

- File size limit (100MB default)
- Secure filename sanitization
- Path traversal protection
- UUID-based temporary files
- Automatic file cleanup (1 hour)
- Session security with secret keys

## Troubleshooting

### Railway Deployment Issues

1. **Build Fails**: Check Python version in `runtime.txt` matches Railway's supported versions
2. **App Crashes**: Check logs in Railway dashboard for detailed errors
3. **File Upload Errors**: Ensure `MAX_CONTENT_LENGTH` is set appropriately
4. **Memory Issues**: Railway's free tier has 512MB RAM limit

### Common Issues

1. **"Invalid document structure"**: Ensure document uses Word's endnote feature
2. **Large files timeout**: Files over 50MB may need increased timeout settings
3. **Style not applying**: Check citation format matches expected pattern

## API Endpoint

### POST `/convert`

**Parameters:**
- `file`: .docx file (required)
- `word_count`: Integer 1-10 (default: 3)
- `format_style`: "bold" or "italic" (default: "bold")
- `citation_style`: Style code (default: "chicago")
- `preview_mode`: Boolean (default: false)

### POST `/preview`

Returns JSON with preview of changes without modifying file.

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/NewFeature`)
3. Commit changes (`git commit -m 'Add NewFeature'`)
4. Push to branch (`git push origin feature/NewFeature`)
5. Open Pull Request

## Testing

```bash
# Run basic tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=citationparserapp tests/
```

## Performance

- Documents < 100 pages: < 2 seconds
- Documents 100-500 pages: 2-10 seconds
- Documents > 500 pages: 10-30 seconds

## License

MIT License - see LICENSE file for details

## Author

Created for academic document processing and citation management.

## Acknowledgments

- Developed for processing academic manuscripts with extensive citations
- Optimized for psychiatric and medical literature
- Railway platform for seamless deployment

## Support

For issues or questions:
- [Open an issue](https://github.com/yourusername/incipit-genie-pro/issues)
- Check [Railway documentation](https://docs.railway.app)
- Review logs in Railway dashboard

## Version History

- v3.3: Production release with Railway optimization
- v3.2: Added preview mode and CMS 17th edition support
- v3.1: Enhanced journal database
- v3.0: Multi-style support
- v2.0: Incipit extraction
- v1.0: Basic endnote conversion
