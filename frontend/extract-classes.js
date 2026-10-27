// Extract className values from .tsx files
const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'src');
const outputFile = path.join(__dirname, 'plans/tailwind-raw.txt');

function extractClassNamesFromFile(filePath) {
    const content = fs.readFileSync(filePath, 'utf8');
    const classNames = new Set();
    // Match className="..."
    const staticMatches = content.match(/className="([^"]*)"/g);
    if (staticMatches) {
        staticMatches.forEach(match => {
            const className = match.replace('className="', '').replace('"', '');
            if (className) classNames.add(className);
        });
    }
    // Match className={`...`} (template literals) - simplistic: capture everything between backticks
    const templateMatches = content.match(/className=`([^`]+)`/g);
    if (templateMatches) {
        templateMatches.forEach(match => {
            const className = match.replace('className=`', '').replace('`', '');
            if (className) classNames.add(className);
        });
    }
    // Also match className={...} but we can't easily parse; skip for now
    return classNames;
}

function walkDir(dir) {
    const items = fs.readdirSync(dir);
    items.forEach(item => {
        const fullPath = path.join(dir, item);
        const stat = fs.statSync(fullPath);
        if (stat.isDirectory()) {
            walkDir(fullPath);
        } else if (item.endsWith('.tsx')) {
            const classNames = extractClassNamesFromFile(fullPath);
            classNames.forEach(cn => console.log(cn));
        }
    });
}

const classNamesSet = new Set();
walkDir(srcDir);

// Write to file
const classNamesArray = Array.from(classNamesSet);
classNamesArray.sort();
fs.writeFileSync(outputFile, classNamesArray.join('\n'), 'utf8');
console.log(`Extracted ${classNamesArray.length} unique class names to ${outputFile}`);