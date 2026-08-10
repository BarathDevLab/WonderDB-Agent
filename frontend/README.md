# AI Database Agent - Frontend

## Overview

This is the frontend presentation layer for the **AI Database Agent**, an Enterprise Text-to-SQL platform. It provides a real-time, responsive user interface designed to seamlessly connect with the FastAPI backend orchestration layer. 

The frontend relies on **Server-Sent Events (SSE)** to stream:
- Live reasoning and execution progress (e.g., retrieving schemas, validating ASTs).
- Tabular result sets from database queries.
- Declarative Chart.js visualization specifications generated directly by the AI.

## Technology Stack

- **Framework**: React 18
- **Build Tool**: Vite
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **Visualizations**: Chart.js (`react-chartjs-2`)

## Features

- **Real-Time SSE Streaming**: Listens to the backend's `/api/v1/agent/stream` endpoint for live state machine transitions.
- **Dynamic Charts**: Renders visual data representations (e.g. Bar, Line) generated on-the-fly by the backend.
- **Data Grids**: Interactive rendering of SQL query execution results.
- **Self-Correction Indicators**: Visual feedback when the AI reflection node catches SQL AST or execution errors and retries.

## Setup Instructions

### Prerequisites

Ensure you have [Node.js](https://nodejs.org/) (v18+) and `npm` installed on your machine.

### Installation

1. **Navigate to the frontend directory** (if you aren't already there):
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

### Running the Development Server

To start the Vite development server with Hot Module Replacement (HMR):

```bash
npm run dev
```

By default, the application will be available at `http://localhost:5173/`. 
*(Note: Ensure your FastAPI backend and MCP server are running locally so the frontend can successfully connect to the endpoints).*

### Building for Production

To compile the TypeScript code and bundle the application for production deployment:

```bash
npm run build
```
This command generates optimized static files in the `dist` directory. You can preview the production build locally by running:

```bash
npm run preview
```
