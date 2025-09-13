# Tutorial Platform

## Overview

This is a Flask-based tutorial platform designed for self-paced learning without traditional user authentication. The application provides a comprehensive learning management system with video content, HTML lessons, quizzes, and progress tracking. It features a hidden admin panel for content management and course administration, while learners can access modules, track progress, take notes, and earn certificates upon completion.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask web application with a single-file architecture (app.py)
- **Session Management**: Server-side sessions using Flask's session system with required SESSION_SECRET environment variable for security
- **File-based Data Storage**: JSON files for configuration and course data (config.json, courses.json)
- **Content Storage**: Static file serving for videos, HTML modules, and downloadable resources

### Frontend Architecture
- **Template Engine**: Jinja2 templates with a base template system for consistent UI
- **CSS Framework**: Bootstrap 5 for responsive design and component styling
- **JavaScript**: Vanilla JavaScript with modular files (main.js for user features, admin.js for admin functionality)
- **Client-side Storage**: localStorage for progress tracking, bookmarks, user notes, and dark mode preferences

### Data Management
- **Course Structure**: JSON-based module system with metadata including titles, descriptions, video URLs, duration, quizzes, and resources
- **Progress Tracking**: Client-side progress storage using localStorage, eliminating need for user accounts
- **Content Organization**: Static file serving from organized directories (data/modules/, static/resources/)

### Authentication Model
- **User Access**: No authentication required for learners
- **Admin Access**: Passcode-based protection for admin panel access at /admin endpoint
- **Session Security**: Admin sessions managed server-side with secure session keys

### Content Delivery
- **Video Streaming**: HTML5 video player with external video URL support
- **Module Content**: HTML file rendering with Markdown support for rich text content
- **Resource Downloads**: Direct file serving for PDFs, ZIPs, and other educational materials
- **Certificate Generation**: PDF generation using ReportLab for course completion certificates

### Interactive Features
- **Quiz System**: JSON-based multiple choice quizzes with client-side validation
- **Search Functionality**: Client-side filtering of modules by title and content keywords
- **Keyboard Navigation**: Arrow key navigation between modules and spacebar for completion marking
- **Bookmarking System**: Star/bookmark modules with localStorage persistence

### Admin Panel Features
- **Content Management**: Full CRUD operations for modules including drag-and-drop reordering using SortableJS
- **Site Customization**: Dynamic theming system with configurable colors, fonts, and branding
- **Import/Export**: ZIP-based course backup and restore functionality
- **Auto-save**: Persistent form data protection using localStorage to prevent data loss

## External Dependencies

### Core Framework Dependencies
- **Flask**: Web application framework for routing, templating, and session management
- **Werkzeug**: WSGI utilities for secure file handling and form processing

### Frontend Libraries
- **Bootstrap 5**: CSS framework loaded via CDN for responsive UI components
- **Bootstrap Icons**: Icon library for consistent iconography throughout the application
- **SortableJS**: Drag-and-drop functionality for module reordering in admin panel

### Document Generation
- **ReportLab**: PDF generation library for creating completion certificates
- **Markdown**: Text-to-HTML conversion for rich content rendering in modules

### File Handling
- **zipfile**: Python standard library for course import/export functionality
- **json**: Configuration and course data serialization/deserialization
- **io**: In-memory file operations for dynamic content generation

### Environment Requirements
- **SESSION_SECRET**: Required environment variable for secure session management
- **File System**: Write permissions for static file uploads and JSON data persistence

### Browser APIs
- **localStorage**: Client-side data persistence for progress, bookmarks, notes, and preferences
- **HTML5 Video API**: Native video playback controls and progress tracking
- **File API**: Client-side file handling for uploads and downloads