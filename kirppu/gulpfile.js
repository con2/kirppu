const gulp = require("gulp");
const gif = require("gulp-if");
const concat = require("gulp-concat-util");
const coffee = require("gulp-coffee");
const fs = require("node:fs");
const path = require("node:path");
const rollup = require("rollup");
const rollup_sucrase = require("@rollup/plugin-sucrase");
const uglify = require("gulp-uglify");
const minify = require("gulp-postcss");
const cssnano = require("cssnano");

const args = require("minimist")(process.argv.slice(2));
const withColor = (c) => (s) => `\x1b[${ c }m${ s }\x1b[39m`;
const colors = {
    // for more colors, see: https://en.wikipedia.org/wiki/ANSI_escape_code#3/4_bit
    red: withColor(31),
    cyan: withColor(36)
};
const log = require("fancy-log");


const pipeline = require("./pipeline");
const SRC = "static_src";
const DEST = "static/kirppu";

// Compression enabled, if run with arguments: --type production
const shouldCompress = args.type === "production";
const debug = args.type === "debug";

const jsHeader = (ctx) => `// ================ ${ctx.index}: ${ctx.original} ================\n\n`;
const cssHeader = (ctx) => `/* ================ ${ctx.index}: ${ctx.original} ================ */\n\n`;


/**
 * Add source (SRC) prefix for all source file names from pipeline definition.
 *
 * @param {Object} def Pipeline group definition value.
 * @returns {Array} Prefixed source files.
 */
const srcPrepend = function(def) {
    function doit(n) {
        const resultName = path.join(SRC, n);
        try {
            fs.statSync(resultName);
        }
        catch (ignored) {
            log(colors.red("File not found (or error): ") + n);
        }
        return resultName;
    }
    if (typeof(def) == "string") {
        return doit(def)
    }
    return def.source_filenames.map(doit)
};

/**
 * Get concat:process function that adds given header to each part of concatenated file.
 *
 * @param header {function} Header template to use.
 * @returns {Function} Function for concat:process.
 */
const fileHeader = function(header) {
    let index = 1;
    return function(src) {
        if (shouldCompress) {
            return src;
        }
        let original = /[/\\]?([^/\\]*)$/.exec(this.history[0]);
        if (original != null) original = original[1]; else original = "?";
        return header({file: this, index: index++, original: original}) + src;
    };
};

const handleError = function(err) {
    log(colors.red("Error: ") + err);
    return this.emit('end');
};

const jsTasks = Object.entries(pipeline.js).map(function([name, def]) {
    const taskName = "js:" + name;
    gulp.task(taskName, function() {
        return gulp.src(srcPrepend(def))
            .pipe(gif(/\.coffee$/, coffee()))
            .on('error', handleError)
            .pipe(concat(def.output_filename, {process: fileHeader(jsHeader)}))
            .pipe(gif(shouldCompress && def.compress, uglify()))
            .pipe(gulp.dest(DEST + "/js/"));
    });
    return taskName;
});

const cssTasks = Object.entries(pipeline.css).map(function([name, def]) {
    const taskName = "css:" + name;
    gulp.task(taskName, function() {
        return gulp.src(srcPrepend(def))
            .pipe(concat(def.output_filename, {process: fileHeader(cssHeader)}))
            .on('error', handleError)
            .pipe(gif(shouldCompress, minify([cssnano()])))
            .pipe(gulp.dest(DEST + "/css/"));
    });
    return taskName;
});

const rollupTasks = Object.entries(pipeline.rollup).map(function([name, def]) {
    const taskName = "rollup:" + name;
    gulp.task(taskName, function() {
        return rollup.rollup({
            input: srcPrepend(def.source_filename),
            plugins: [
                rollup_sucrase({
                    jsxPragma: 'redom.el',
                    transforms: ['jsx'],
                    production: !debug,
                })
            ]
        }).then(bundle => {
            return bundle.write({
                file: DEST + "/" + def.output_filename,
                name: def.output_name,
                format: 'iife'
            });
        });
    });
    return taskName;
});

const staticTasks = Object.entries(pipeline.static).map(function([name, def]) {
    const taskName = "static:" + name;
    gulp.task(taskName, function() {
        let _to = DEST;
        const options = {
            encoding: false,
        };
        if (def.dest) {
            _to = path.join(_to, def.dest);
        }
        else {
            options["base"] = SRC;
        }
        return gulp.src(srcPrepend(def), options)
            .pipe(gulp.dest(_to))
    });
    return taskName;
});

gulp.task("pipeline", gulp.series([]
    .concat(jsTasks)
    .concat(cssTasks)
    .concat(rollupTasks)
    .concat(staticTasks)
));

gulp.task("default", gulp.series("pipeline"));

/**
 * Simple wildcard pattern matcher.
 */
const simpleWildcard = function(pattern, file) {
    if (pattern) {
        if (Array.isArray(pattern)) {
            for (const element of pattern) {
                if (simpleWildcard(element, file)) {
                    return true;
                }
            }
            return false;
        }
        return new RegExp(pattern
            .replace(".", "\.")
            .replace("?", ".")
            .replace("*", ".*")
        ).exec(file) != null
    }
    return false
}

/**
 * Find name of pipeline task by source filename.
 *
 * @param haystack {Object} Pipeline group container (js or css object).
 * @param file {string} Filename to find for.
 * @returns {string|undefined|*} Pipeline group name or undefined.
 */
const findTask = function(haystack, file) {
    const trimStartDots = /^\.+/;
    const cleanedFile = file.replace(trimStartDots, "");
    const result = Object.entries(haystack).find(([group, def]) =>
        def.source_filenames?.find((fn) =>
            cleanedFile.endsWith(fn.replace(trimStartDots, ""))
        ) || simpleWildcard(def.watch, file)
    );
    return result ? result[0] : null;
};

/**
 * Start task by watch or --file commandline argument.
 *
 * @param file Filename argument, which file has been changed.
 * @returns {boolean} True if task was run. Otherwise false.
 */
const startFileTask = function(file) {
    // Replace '\' with '/' so Windows file paths work.
    const filename = file.replace(/\\/g, "/");

    // Find first matching task from pipeline groups.
    const task = Object.entries(pipeline).map(([typeGroup, typeCfgDicts]) => {
        const taskName = findTask(typeCfgDicts, filename);
        return taskName != null ? `${typeGroup}:${taskName}` : null;
    }).find((v) => v != null);

    if (task != null) {
        gulp.series(task)();
        return true;
    }
    return false;
};

// For file watcher:  build --file $FilePathRelativeToProjectRoot$
gulp.task("build", function() {
    const file = args.file;
    if (file == null) {
        log(colors.red("Need argument: --file FILE"));
    }
    else if (!(startFileTask(file))) {
        log(colors.red("Target file not found in pipeline.js: " + file));
    }
});


gulp.task("watch", function() {
    gulp.watch(SRC + "/**/*").on("change", function(file) {
        if (!(startFileTask(file))) {
            log(colors.red("Target file not found in pipeline.js: " + file));
        }
    });
    gulp.watch("pipeline.js").on("change", function() {
        log("Pipeline configuration changed. Please restart " + colors.cyan("gulp watch"));
    })
});
