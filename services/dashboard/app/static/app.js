(function () {
    function getStorage(type) {
        try {
            return window[type];
        } catch (error) {
            return null;
        }
    }

    var sessionStore = getStorage("sessionStorage");
    var localStore = getStorage("localStorage");

    function getStoredValue(store, key) {
        if (!store) {
            return null;
        }
        try {
            return store.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function setStoredValue(store, key, value) {
        if (!store) {
            return;
        }
        try {
            store.setItem(key, value);
        } catch (error) {
            /* Ignore storage failures in privacy-restricted contexts. */
        }
    }

    function initBootSequence() {
        var title = document.querySelector(".header__title");
        if (!title || getStoredValue(sessionStore, "valhalla-booted")) {
            document.body.classList.remove("booting");
            return;
        }

        var original = title.textContent;
        var chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%&*";
        var iterations = 0;
        var interval = window.setInterval(function () {
            title.textContent = original
                .split("")
                .map(function (char, index) {
                    if (char === " ") {
                        return " ";
                    }
                    if (index < iterations) {
                        return original[index];
                    }
                    return chars[Math.floor(Math.random() * chars.length)];
                })
                .join("");

            iterations += 1;
            if (iterations > original.length) {
                window.clearInterval(interval);
                title.innerHTML = "<span>Valhalla</span> Capital";
                document.body.classList.remove("booting");
                setStoredValue(sessionStore, "valhalla-booted", "1");
            }
        }, 50);
    }

    function initClock() {
        var clock = document.getElementById("clock");
        if (!clock) {
            return;
        }

        var offset = 0;

        function updateClock() {
            var now = new Date(Date.now() + offset);
            var hours = String(now.getUTCHours()).padStart(2, "0");
            var minutes = String(now.getUTCMinutes()).padStart(2, "0");
            var seconds = String(now.getUTCSeconds()).padStart(2, "0");
            clock.textContent = hours + ":" + minutes + ":" + seconds + " UTC";
        }

        fetch("/api/time")
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                var serverTime = new Date(data.utc).getTime();
                offset = serverTime - Date.now();
                updateClock();
            })
            .catch(function () {
                updateClock();
            });

        updateClock();
        window.setInterval(updateClock, 1000);
    }

    function initSoundscape() {
        var button = document.getElementById("sound-toggle");
        var icon = document.getElementById("sound-icon");
        if (!button || !icon) {
            return;
        }

        var state = {
            active: false,
            audioCtx: null,
            humGain: null,
            hum2Gain: null,
            suspendTimer: null,
        };

        function initAudio() {
            if (state.audioCtx) {
                return;
            }

            var AudioContextCtor = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextCtor) {
                return;
            }

            state.audioCtx = new AudioContextCtor();

            var hum = state.audioCtx.createOscillator();
            hum.type = "sine";
            hum.frequency.value = 60;

            var hum2 = state.audioCtx.createOscillator();
            hum2.type = "sine";
            hum2.frequency.value = 120;

            state.humGain = state.audioCtx.createGain();
            state.hum2Gain = state.audioCtx.createGain();
            state.humGain.gain.value = 0;
            state.hum2Gain.gain.value = 0;

            hum.connect(state.humGain);
            hum2.connect(state.hum2Gain);
            state.humGain.connect(state.audioCtx.destination);
            state.hum2Gain.connect(state.audioCtx.destination);

            hum.start();
            hum2.start();
        }

        function playClick() {
            if (!state.audioCtx || !state.active) {
                return;
            }

            var osc = state.audioCtx.createOscillator();
            var gain = state.audioCtx.createGain();
            osc.type = "square";
            osc.frequency.value = 800 + Math.random() * 400;
            gain.gain.value = 0.03;
            gain.gain.exponentialRampToValueAtTime(
                0.001,
                state.audioCtx.currentTime + 0.06
            );
            osc.connect(gain);
            gain.connect(state.audioCtx.destination);
            osc.start();
            osc.stop(state.audioCtx.currentTime + 0.06);
        }

        function enable() {
            initAudio();
            if (!state.audioCtx) {
                return;
            }

            if (state.suspendTimer) {
                window.clearTimeout(state.suspendTimer);
                state.suspendTimer = null;
            }

            if (state.audioCtx.state === "suspended") {
                state.audioCtx.resume();
            }

            state.humGain.gain.setTargetAtTime(0.015, state.audioCtx.currentTime, 0.5);
            state.hum2Gain.gain.setTargetAtTime(0.008, state.audioCtx.currentTime, 0.5);
            state.active = true;
            icon.textContent = "\u266B";
            button.classList.add("footer__sound-toggle--active");
            setStoredValue(localStore, "valhalla-ambient", "1");
        }

        function disable() {
            if (state.audioCtx) {
                state.humGain.gain.setTargetAtTime(0, state.audioCtx.currentTime, 0.3);
                state.hum2Gain.gain.setTargetAtTime(0, state.audioCtx.currentTime, 0.3);

                state.suspendTimer = window.setTimeout(function () {
                    if (state.audioCtx && state.audioCtx.state === "running" && !state.active) {
                        state.audioCtx.suspend();
                    }
                }, 800);
            }

            state.active = false;
            icon.textContent = "\u266B";
            button.classList.remove("footer__sound-toggle--active");
            setStoredValue(localStore, "valhalla-ambient", "0");
        }

        button.addEventListener("click", function () {
            if (state.active) {
                disable();
            } else {
                enable();
            }
        });

        document.body.addEventListener("htmx:afterSwap", function () {
            playClick();
        });

        document.addEventListener("visibilitychange", function () {
            if (!state.audioCtx || !state.active) {
                return;
            }
            if (document.visibilityState === "hidden") {
                state.audioCtx.suspend();
            } else {
                state.audioCtx.resume();
            }
        });

        if (getStoredValue(localStore, "valhalla-ambient") === "1") {
            button.classList.add("footer__sound-toggle--remembered");
        }
    }

    function updateHealthState() {
        var downCount = document.querySelector(".summary__count--down");
        if (!downCount) {
            document.body.classList.remove("systems-degraded");
            return;
        }

        if (parseInt(downCount.textContent, 10) > 0) {
            document.body.classList.add("systems-degraded");
        } else {
            document.body.classList.remove("systems-degraded");
        }
    }

    function parseJsonData(raw, fallback) {
        if (!raw) {
            return fallback;
        }

        try {
            return JSON.parse(raw);
        } catch (error) {
            return fallback;
        }
    }

    function renderEmptyChart(container) {
        container.innerHTML =
            '<svg viewBox="0 0 400 160" class="portfolio-chart">' +
            '<text x="200" y="80" text-anchor="middle" fill="var(--text-dim)" ' +
            'font-size="11" font-family="sans-serif">No data yet</text>' +
            "</svg>";
    }

    function initPortfolioChart() {
        var container = document.querySelector("[data-portfolio-chart]");
        if (!container) {
            return;
        }

        var series = parseJsonData(container.dataset.series, { pnl: [], value: [] });
        var snapshots = parseJsonData(container.dataset.snapshots, []);
        if (snapshots && snapshots.length > 1) {
            series.value = snapshots;
        }

        var hasPnl = series.pnl && series.pnl.length >= 2;
        var hasValue = series.value && series.value.length >= 2;
        if (!hasPnl && !hasValue) {
            return;
        }

        var buttons = Array.prototype.slice.call(
            document.querySelectorAll("[data-chart-mode]")
        );

        function xPosition(index, length, width, padding) {
            return padding.left + (index / (length - 1)) * width;
        }

        function renderChart(data, mode) {
            if (!data || data.length < 2) {
                renderEmptyChart(container);
                return;
            }

            var width = 400;
            var height = 160;
            var padding = { top: 16, right: 12, bottom: 24, left: 52 };
            var chartWidth = width - padding.left - padding.right;
            var chartHeight = height - padding.top - padding.bottom;

            var values = data.map(function (point) {
                return point.value;
            });
            var minValue = Math.min.apply(null, values);
            var maxValue = Math.max.apply(null, values);
            var range = maxValue - minValue || 1;
            minValue -= range * 0.15;
            maxValue += range * 0.15;
            range = maxValue - minValue;

            function yPosition(value) {
                return (
                    padding.top +
                    chartHeight -
                    ((value - minValue) / range) * chartHeight
                );
            }

            var zeroLine = "";
            if (minValue < 0 && maxValue > 0) {
                var zeroY = yPosition(0);
                zeroLine =
                    '<line x1="' +
                    padding.left +
                    '" y1="' +
                    zeroY +
                    '" x2="' +
                    (width - padding.right) +
                    '" y2="' +
                    zeroY +
                    '" stroke="rgba(255,255,255,0.12)" stroke-width="1" stroke-dasharray="3,3"/>';
            }

            var path =
                "M" +
                xPosition(0, data.length, chartWidth, padding) +
                "," +
                yPosition(data[0].value);
            for (var i = 1; i < data.length; i += 1) {
                path +=
                    " H" +
                    xPosition(i, data.length, chartWidth, padding) +
                    " V" +
                    yPosition(data[i].value);
            }

            var fillBase =
                minValue < 0 && maxValue > 0 ? yPosition(0) : padding.top + chartHeight;
            var fillPath =
                path +
                " V" +
                fillBase +
                " H" +
                xPosition(0, data.length, chartWidth, padding) +
                " Z";

            var lastValue = data[data.length - 1].value;
            var lineColor = "var(--lilac)";
            var fillColor = "rgba(205, 180, 255, 0.06)";
            if (mode !== "value") {
                lineColor = lastValue >= 0 ? "var(--cyan)" : "var(--pink)";
                fillColor =
                    lastValue >= 0
                        ? "rgba(84, 229, 208, 0.06)"
                        : "rgba(255, 107, 157, 0.06)";
            }

            var gridLines = "";
            var labels = "";
            for (var grid = 0; grid <= 4; grid += 1) {
                var gridY = padding.top + (grid / 4) * chartHeight;
                var gridValue = maxValue - (grid / 4) * range;
                gridLines +=
                    '<line x1="' +
                    padding.left +
                    '" y1="' +
                    gridY +
                    '" x2="' +
                    (width - padding.right) +
                    '" y2="' +
                    gridY +
                    '" stroke="rgba(255,255,255,0.03)" stroke-width="1"/>';
                labels +=
                    '<text x="' +
                    (padding.left - 6) +
                    '" y="' +
                    (gridY + 3) +
                    '" text-anchor="end" fill="var(--text-dim)" font-size="8" font-family="monospace">' +
                    (gridValue >= 0 ? "$" : "-$") +
                    Math.abs(Math.round(gridValue)).toLocaleString() +
                    "</text>";
            }

            var dots = "";
            for (var dx = padding.left; dx < width - padding.right; dx += 14) {
                for (var dy = padding.top; dy < height - padding.bottom; dy += 14) {
                    dots +=
                        '<circle cx="' +
                        dx +
                        '" cy="' +
                        dy +
                        '" r="0.4" fill="rgba(255,255,255,0.05)"/>';
                }
            }

            var timeLabels = "";
            var labelCount = Math.min(data.length, 4);
            for (var labelIndex = 0; labelIndex < labelCount; labelIndex += 1) {
                var pointIndex = Math.round(
                    (labelIndex * (data.length - 1)) / (labelCount - 1 || 1)
                );
                var pointDate = new Date(data[pointIndex].time);
                var label =
                    pointDate.getMonth() + 1 + "/" + pointDate.getDate();
                timeLabels +=
                    '<text x="' +
                    xPosition(pointIndex, data.length, chartWidth, padding) +
                    '" y="' +
                    (height - 6) +
                    '" text-anchor="middle" fill="var(--text-dim)" font-size="8" font-family="monospace">' +
                    label +
                    "</text>";
            }

            var valuePrefix = mode === "value" ? "$" : lastValue >= 0 ? "+$" : "-$";
            var valueDisplay = mode === "value" ? lastValue : Math.abs(lastValue);
            var valueLabel =
                '<text x="' +
                (width - padding.right) +
                '" y="' +
                (padding.top - 4) +
                '" text-anchor="end" fill="' +
                lineColor +
                '" font-size="11" font-family="monospace" font-weight="600">' +
                valuePrefix +
                valueDisplay.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                }) +
                "</text>";

            var circles = data
                .map(function (point, index) {
                    return (
                        '<circle cx="' +
                        xPosition(index, data.length, chartWidth, padding) +
                        '" cy="' +
                        yPosition(point.value) +
                        '" r="2" fill="var(--bg-deep)" stroke="' +
                        lineColor +
                        '" stroke-width="1"/>'
                    );
                })
                .join("");

            container.innerHTML =
                '<svg viewBox="0 0 ' +
                width +
                " " +
                height +
                '" class="portfolio-chart">' +
                dots +
                gridLines +
                zeroLine +
                labels +
                timeLabels +
                '<path d="' +
                fillPath +
                '" fill="' +
                fillColor +
                '"/>' +
                '<path d="' +
                path +
                '" fill="none" stroke="' +
                lineColor +
                '" stroke-width="1.5" stroke-linecap="square"/>' +
                circles +
                valueLabel +
                "</svg>";
        }

        function switchChart(mode) {
            buttons.forEach(function (button) {
                button.classList.toggle(
                    "chart-toggle__btn--active",
                    button.dataset.chartMode === mode
                );
            });

            var data = series[mode];
            if (!data || data.length < 2) {
                renderEmptyChart(container);
                return;
            }

            renderChart(data, mode);
        }

        buttons.forEach(function (button) {
            button.addEventListener("click", function () {
                switchChart(button.dataset.chartMode);
            });
        });

        if (hasValue) {
            switchChart("value");
        } else {
            switchChart("pnl");
        }
    }

    function initTradeRowExpansion() {
        document.addEventListener("click", function (event) {
            var row = event.target.closest(".trade-row--expandable");
            if (!row) {
                return;
            }
            if (event.target.closest("a")) {
                return;
            }
            row.classList.toggle("trade-row--expanded");
        });
    }

    function init() {
        initBootSequence();
        initClock();
        initSoundscape();
        updateHealthState();
        initPortfolioChart();
        initTradeRowExpansion();

        document.body.addEventListener("htmx:afterSwap", function () {
            updateHealthState();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
