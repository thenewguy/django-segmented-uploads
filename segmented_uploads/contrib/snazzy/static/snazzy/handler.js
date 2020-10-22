(function(window, console){
    function checkReq(requirement, url, scope) {
        scope = scope || window;
        if (!scope.hasOwnProperty(requirement)) {
            throw "Missing required dependency: " + requirement + " (try " + url + ")";
        }
        return scope[requirement];
    }
    
    var $ = checkReq("$", "https://cdn.jsdelivr.net/npm/jquery@3.4.1/dist/jquery.min.js"),
        Cookies = checkReq("Cookies", "https://cdn.jsdelivr.net/npm/js-cookie@2.2.1/src/js.cookie.min.js"),
        Promise = checkReq("Promise", "https://cdn.jsdelivr.net/npm/es6-promise@4.2.8/dist/es6-promise.auto.min.js"),
        Resumable = checkReq("Resumable", "https://cdn.jsdelivr.net/npm/resumablejs@1.1.0/resumable.min.js"),
        SparkMD5 = checkReq("SparkMD5", "https://cdn.jsdelivr.net/npm/spark-md5@3.0.0/spark-md5.js");
        checkReq("widget", "https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/ui/widget.min.js", $);
        checkReq("progressbar", "https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/ui/widgets/progressbar.js", checkReq("ui", "https://cdn.jsdelivr.net/npm/jquery-ui@1.12.1/ui/widgets/progressbar.js", $));

    if (Resumable().support) {
        $(function(){
            // calculateHash() is adapted from https://github.com/satazor/js-spark-md5/blob/3.0.0/README.md#hash-a-file-incrementally
            var blobSlice = File.prototype.slice || File.prototype.mozSlice || File.prototype.webkitSlice;
            function calculateHash(file, cb, startByte, endByte, chunkCountLimit) {
                console.log('calculateHash starting');
            
                startByte = startByte || 0;
                endByte = endByte || 0;
                
                var chunkSize = 2097152, // Read in chunks of 2MB
                    chunks = Math.ceil(file.size / chunkSize),
                    currentChunk = 0,
                    spark = new SparkMD5.ArrayBuffer(),
                    fileReader = new FileReader();
                
                if (chunkCountLimit && chunkCountLimit < chunks) {
                    chunks = chunkCountLimit;
                }
                
                if (endByte) {
                    chunkSize = endByte - startByte;
                    chunks = 1;
                }
            
                fileReader.onload = function (e) {
                    console.log('read chunk nr', currentChunk + 1, 'of', chunks);
                    spark.append(e.target.result); // Append array buffer
                    currentChunk++;
            
                    if (currentChunk < chunks) {
                        loadNext();
                    } else {
                        console.log('finished loading');
                        var digest = spark.end(); // Compute hash
                        console.info('computed hash', digest);
                        cb(digest);
                    }
                };
            
                fileReader.onerror = function () {
                    console.warn('oops, something went wrong.');
                };
            
                function loadNext() {
                    var start, end;
                    
                    if (endByte) {
                        start = startByte;
                        end = endByte;
                    } else {
                        start = currentChunk * chunkSize;
                        end = ((start + chunkSize) >= file.size) ? file.size : start + chunkSize;
                    }
            
                    fileReader.readAsArrayBuffer(blobSlice.call(file, start, end));
                }
            
                loadNext();
            }
            
            function getFileName(file) {
                // necessary per https://github.com/23/resumable.js/blob/v1.1.0/resumable.js#L434
                return file.fileName || file.name;
            }
        
            $("[data-segmented-upload-endpoint]").each(function(i, el){
                var $el = $(el);
                var endpoint = $el.attr("data-segmented-upload-endpoint");
                
                $.ajax({
                    url: endpoint,
                    method: "OPTIONS",
                    xhrFields: {
                        withCredentials: true
                    },
                    dataType: "json",
                    error: function(){
                        console.log('failed to get options');
                    },
                    success: function(data){
                        process(data.validation);
                    }
                });
                
                function process(settings) {
                    var maxFileSize = settings.segment_limit * settings.segment_allowable_size;
                    
                    var r = new Resumable({
                        target: endpoint,
                        chunkSize: settings.segment_allowable_size,
                        forceChunkSize: true,
                        permanentErrors: [400, 403, 409, 500],
                        withCredentials: true,
                        preprocess: function(chunk){
                            calculateHash(chunk.fileObj.file, function(digest){
                                chunk.md5sum = digest;
                                chunk.preprocessFinished();
                            }, chunk.startByte, chunk.endByte);
                        },
                        query: function(file, chunk){
                            return {digest: chunk.md5sum, algorithm: 'md5'};
                        },
                        headers: {
                            'X-CSRFToken': Cookies.get('csrftoken'),
                        },
                        generateUniqueIdentifier: function(file, event){
                            $.each(r.files, function(i, f){
                                // resumable.js supports multiple file uploads, but
                                // this widget is designed for one file per input. so
                                // we clear the previous files here instead of using
                                // the maxFiles option so that the user can easily
                                // correct picking the wrong file
                                console.log('Removing previosuly selected file:');
                                console.log(f);
                                r.removeFile(f);
                            });
                            return new Promise(function(resolve, reject){
                                calculateHash(file, function(digest){
                                    var identifier = JSON.stringify({
                                        partialDigest: digest,
                                        chunkSize: r.getOpt('chunkSize'),
                                        forceChunkSize: r.getOpt('forceChunkSize'),
                                        name: getFileName(file),
                                        size: file.size
                                    });
                                    console.log('generated unique identifier: ' + identifier);
                                    resolve(identifier);
                                // hashing the whole file might take a long time so only
                                // use the first 3 chunks here and assume uniqueness per
                                // user when combined with the other parameters
                                }, null, null, 3);
                            });
                        },
                        identifierParameterName: 'identifier',
                        fileNameParameterName: 'filename',
                        chunkNumberParameterName: 'index',
                        totalChunksParameterName: 'count',
                        currentChunkSizeParameterName: 'segment_size',
                        totalSizeParameterName: 'total_size'
                    });
                    
                    console.log('created resumable object');
                    console.log(r);
                    
                    r.on('fileSuccess', function(file){
                        // trigger materialization
                        var pollDelay = 3000;
                        $.ajax({
                            url: endpoint,
                            method: "POST",
                            xhrFields: {
                                withCredentials: true
                            },
                            data: {
                                csrfmiddlewaretoken: Cookies.get('csrftoken'),
                                identifier: file.uniqueIdentifier,
                                digest: file.md5sum,
                                algorithm: 'md5'
                            },
                            dataType: "text",
                            error: function(jqXHR){
                                if (jqXHR.status == 300) {
                                    this.url = jqXHR.responseText;
                                    console.log("polling redirected to " + this.url);
                                    this.success();
                                } else {
                                    clearErrors();
                                    addError("file upload failed to process");
                                    displayErrors();
                                    
                                    $progress.progressbar("value", 100);
                                    progressIsFailure();
                                    
                                    placeBrowse();
                                    
                                    started = false;
                                }
                            },
                            success: function(secret){
                                var opts = this;
                                if (secret) {
                                    console.log("materialization success");
                                    console.log(secret);
                                    
                                    $el.val(secret);
                                    $progress.progressbar("value", false);
                                    progressIsSuccess();
                                    
                                    $form.off(namespaced_submit_event).submit();
                                } else {
                                    console.log("materialization pending; continue polling " + opts.url + " in " + pollDelay +  " milliseconds.");
                                    $progress.progressbar("value", false);
                                    setTimeout(function(){
                                        $.ajax(opts);
                                    }, pollDelay);
                                }
                            },
                        });
                    });
                    
                    var $form = $el.parentsUntil("form").parent();
                    var required = $el.prop("required");
                    $el.prop("required", false);
                    $el.attr("type", "hidden");
                    
                    function validateFileSize(file) {
                        if (maxFileSize < file.size) {
                            addError('File is too large. File size must be less than ' + maxFileSize + ' bytes. This one is ' + file.size + ' bytes.', file);
                        }
                    }
                    
                    function validateFile(file) {
                        console.log('validateFile');
                        console.log(file);
                    
                        validateFileSize(file);
                    }
                    
                    function handleFileAddedValidation(file) {
                        validateFile(file);
                        if (errors.length) {
                            displayErrors();
                            return false;
                        }
                        return true;
                    }
                    
                    r.on('fileAdded', function(file){
                        clearErrors();
                        destroyProgress();
                        
                        $browse.text(file.fileName);
                        
                        if (handleFileAddedValidation(file)) {
                            // calculate the whole file hash here and we will wait for it
                            // to become available before finalizing the upload
                            calculateHash(file.file, function(md5sum){
                                file.md5sum = md5sum;
                            });
                        }
                        console.log('file #' + r.files.length + ' added');
                        console.log(file);
                    });
                    
                    var $browse = $("<span class='snazzy-segmented-uploads browse'></span>");
                    function placeBrowse() {
                        $browse.text("No selection yet.");
                        $el.after($browse);
                    }
                    placeBrowse();
                    r.assignBrowse($browse[0]);
                    
                    var $progress = $("<div class='snazzy-segmented-uploads'>"),
                        progressActive = false;
                    
                    function progressIsPending() {
                        $progress.removeClass('failure success').addClass('pending');
                    }
                    
                    function progressIsSuccess() {
                        $progress.removeClass('pending failure').addClass('success');
                    }
                    
                    function progressIsFailure() {
                        $progress.removeClass('pending success').addClass('failure');
                    }
                    
                    function createProgress() {
                        $el.after($progress);
                        $progress.progressbar({
                            value: false
                        });
                        progressActive = true;
                        progressIsPending();
                    }
                    
                    function destroyProgress() {
                        if (progressActive) {
                            $progress.progressbar("destroy");
                            $progress.remove();
                            progressActive = false;
                        }
                    }
                    
                    r.on('progress', function(){
                        $progress.progressbar("value", r.progress() * 100);
                        progressIsPending();
                    });
                    
                    var errors = [],
                        $errors = $("<ul tabindex='-1' class='snazzy-segmented-uploads errors'>");
                    r.on('error', function(message, file){
                        var data;
                        try {
                            data = JSON.parse(message);
                        } catch(e) {
                            addError(message, file);
                            return;
                        }
                        var handler = function (i, e) {
                            addError(e, file);
                        };
                        for (var key in data) {
                            if (data.hasOwnProperty(key)) {
                                $.each(data[key], handler);
                            }
                        }
                    });
                    
                    function clearErrors() {
                        $errors.remove();
                        $errors.empty();
                        errors = [];
                    }
                    
                    function addError(message, file) {
                        errors.push({message: message, file: file});
                    }
                    
                    function displayErrors() {
                        $errors.empty();
                        $el.before($errors);
                        $.each(errors, function(i, e){
                            $errors.append("<li>" + e.message + "</li>");
                        });
                    }
                    
                    r.on('complete', function(){
                        if (!errors.length) {
                            $progress.progressbar("value", false);
                            progressIsPending();
                        } else {
                            destroyProgress();
                            displayErrors();
                            placeBrowse();
                            started = false;
                        }
                    });
                    
                    var namespaced_submit_event = "submit.snazzy-segmented-uploads." + $el[0].id;
                    
                    function fileCount() {
                        console.log(r);
                        return r.files.length;
                    }
                    
                    function filesAreHashed() {
                        console.log(r);
                        var result = true;
                        $.each(r.files, function(i, f) {
                            console.log(f);
                            result = (result && !!f.md5sum) ? true : false;
                        });
                        return result;
                    }
                    
                    var started = false;
                    $form.on(namespaced_submit_event, function(event){
                        if (r.isUploading() || (required && !$el.val()) || (fileCount() && !$el.val())) {
                            console.log(namespaced_submit_event + ' is still pending');
                            event.preventDefault();
                            
                            if (!started) {
                            
                                if (errors.length) {
                                    console.log('Cannot upload because there are errors to correct.');
                                    displayErrors();
                                    $errors.focus();
                                } else if (fileCount()) {
                                    started = true;
                                    createProgress();
                                    
                                    /* too late to change your mind! */
                                    $browse.remove();
                                    
                                    var interval = setInterval(function(){
                                        if (filesAreHashed()) {
                                            clearInterval(interval);
                                            r.upload();
                                        } else {
                                            console.log('waiting on file digest to start upload');
                                        }
                                    }, 100);
                                    
                                } else if (required) {
                                    clearErrors();
                                    addError('This field is required! Please select a file to continue.');
                                    displayErrors();
                                }
                                
                            }
                            
                        }
                    });
                }
            });
        });
    }
})(window, window.console);
