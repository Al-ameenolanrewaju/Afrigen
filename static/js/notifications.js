(function () {
    'use strict';

    var categories = ['all', 'general', 'generation', 'billing', 'security', 'movie_studio'];
    var triggers = Array.prototype.slice.call(document.querySelectorAll('[data-notification-trigger]'));
    var overlay = document.querySelector('[data-notification-overlay]');
    var panel = overlay && overlay.querySelector('.notification-panel');
    var panelList = overlay && overlay.querySelector('[data-notification-list]');
    var panelState = overlay && overlay.querySelector('[data-notification-state]');
    var unreadElements = Array.prototype.slice.call(document.querySelectorAll('[data-notification-unread]'));
    var badgeElements = Array.prototype.slice.call(document.querySelectorAll('[data-notification-badge]'));
    var panelCategory = 'all';
    var panelRequestId = 0;
    var historyRequestId = 0;
    var busyIds = new Set();
    var history = document.querySelector('[data-notification-history]');

    function setUnreadCount(count) {
        count = Number(count) || 0;
        unreadElements.forEach(function (element) { element.textContent = String(count); });
        badgeElements.forEach(function (element) {
            element.textContent = count > 99 ? '99+' : String(count);
            element.classList.toggle('is-visible', count > 0);
            element.setAttribute('aria-label', count + ' unread notifications');
        });
    }

    function showState(element, message, isError, retry) {
        if (!element) return;
        element.replaceChildren();
        element.classList.add('is-visible');
        element.classList.toggle('is-error', Boolean(isError));
        element.textContent = message;
        if (retry) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'notification-item-action ms-2';
            button.textContent = 'Try again';
            button.addEventListener('click', retry);
            element.appendChild(button);
        }
    }

    function hideState(element) {
        if (!element) return;
        element.classList.remove('is-visible', 'is-error');
        element.replaceChildren();
    }

    function safeDestination(link) {
        if (typeof link !== 'string' || !link.trim()) return null;
        try {
            var destination = new URL(link, window.location.origin);
            return destination.origin === window.location.origin ? destination.href : null;
        } catch (_error) {
            return null;
        }
    }

    function formatTimestamp(value) {
        if (!value) return 'Recently';
        var date = new Date(value);
        if (Number.isNaN(date.getTime())) return 'Recently';
        return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
    }

    function categoryLabel(category) {
        return category === 'movie_studio' ? 'Movie Studio' : category.charAt(0).toUpperCase() + category.slice(1);
    }

    function renderNotifications(list, notifications, state) {
        list.replaceChildren();
        hideState(state);
        if (!notifications.length) {
            showState(state, 'You’re all caught up. New activity will appear here.', false);
            return;
        }

        notifications.forEach(function (notification) {
            var item = document.createElement('article');
            item.className = 'notification-item' + (notification.is_read ? '' : ' is-unread');
            var indicator = document.createElement('span');
            indicator.className = 'notification-item-indicator';
            indicator.setAttribute('aria-hidden', 'true');
            var body = document.createElement('div');
            body.className = 'notification-item-body';
            var heading = document.createElement('div');
            heading.className = 'notification-item-heading';
            var title = document.createElement('h3');
            title.className = 'notification-item-title';
            title.textContent = notification.title || 'Notification';
            heading.appendChild(title);

            if (!notification.is_read) {
                var readButton = document.createElement('button');
                readButton.type = 'button';
                readButton.className = 'notification-item-action';
                readButton.textContent = 'Mark read';
                readButton.setAttribute('aria-label', 'Mark ' + (notification.title || 'notification') + ' as read');
                readButton.disabled = busyIds.has(notification.id);
                readButton.addEventListener('click', function () {
                    markOneRead(notification.id, readButton, state);
                });
                heading.appendChild(readButton);
            }

            var message = document.createElement('p');
            message.className = 'notification-item-message';
            message.textContent = notification.message || '';
            var meta = document.createElement('div');
            meta.className = 'notification-item-meta';
            var category = document.createElement('span');
            category.className = 'notification-item-category';
            category.textContent = categoryLabel(notification.category || 'general');
            var timestamp = document.createElement('time');
            timestamp.dateTime = notification.created_at || '';
            timestamp.textContent = formatTimestamp(notification.created_at);
            meta.append(category, timestamp);
            body.append(heading, message, meta);

            var destination = safeDestination(notification.link);
            if (destination) {
                var link = document.createElement('a');
                link.className = 'notification-item-link';
                link.href = destination;
                link.textContent = 'View details';
                link.addEventListener('click', function (event) {
                    if (notification.is_read) return;
                    event.preventDefault();
                    markOneRead(notification.id, link, state).then(function () {
                        window.location.assign(destination);
                    }).catch(function () {});
                });
                body.appendChild(link);
            }
            item.append(indicator, body);
            list.appendChild(item);
        });
    }

    function requestJson(url, options) {
        return fetch(url, options || {}).then(function (response) {
            return response.json().catch(function () {
                throw new Error('The server returned an unreadable response.');
            }).then(function (data) {
                if (!response.ok) throw new Error(data.error || 'Unable to load notifications.');
                return { data: data, response: response };
            });
        });
    }

    function panelUrl() {
        var params = new URLSearchParams({ page: '1', per_page: '20', category: panelCategory, status: 'all' });
        return '/api/notifications/history?' + params.toString();
    }

    function loadPanel() {
        if (!overlay || !panelList) return Promise.resolve();
        var requestId = ++panelRequestId;
        showState(panelState, 'Loading notifications…', false);
        return requestJson(panelUrl()).then(function (result) {
            if (requestId !== panelRequestId) return;
            setUnreadCount(result.data.unread_count);
            renderNotifications(panelList, result.data.notifications, panelState);
        }).catch(function (error) {
            if (requestId === panelRequestId) showState(panelState, error.message, true, loadPanel);
        });
    }

    function updateCategoryButtons(container, selected) {
        if (!container) return;
        container.querySelectorAll('[data-notification-category]').forEach(function (button) {
            var active = button.dataset.notificationCategory === selected;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function updateStatusButtons(container, selected) {
        if (!container) return;
        container.querySelectorAll('[data-notification-status]').forEach(function (button) {
            var active = button.dataset.notificationStatus === selected;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function openPanel(trigger) {
        if (!overlay || !panel) return;
        overlay.hidden = false;
        overlay.setAttribute('aria-hidden', 'false');
        panel.setAttribute('aria-modal', String(window.matchMedia('(max-width: 991.98px)').matches));
        triggers.forEach(function (button) { button.setAttribute('aria-expanded', 'true'); });
        panelCategory = 'all';
        updateCategoryButtons(overlay, panelCategory);
        loadPanel();
        var closeButton = overlay.querySelector('[data-notification-close]');
        if (closeButton) closeButton.focus();
        panel.dataset.returnFocus = trigger && trigger.id ? trigger.id : '';
    }

    function closePanel() {
        if (!overlay || !panel || overlay.hidden) return;
        overlay.hidden = true;
        overlay.setAttribute('aria-hidden', 'true');
        triggers.forEach(function (button) { button.setAttribute('aria-expanded', 'false'); });
        var returnFocusId = panel.dataset.returnFocus;
        var returnFocus = returnFocusId && document.getElementById(returnFocusId);
        if (returnFocus) returnFocus.focus();
    }

    function markOneRead(id, control, errorState) {
        if (busyIds.has(id)) return Promise.reject(new Error('This notification is already being updated.'));
        busyIds.add(id);
        if (control) control.disabled = true;
        return requestJson('/api/notifications/' + encodeURIComponent(id) + '/read', { method: 'POST' })
            .then(function () {
                return Promise.all([loadPanel(), loadHistory()]);
            })
            .catch(function (error) {
                if (control) control.disabled = false;
                var retry = errorState === panelState ? loadPanel : loadHistory;
                showState(errorState || panelState, error.message, true, retry);
                throw error;
            })
            .finally(function () { busyIds.delete(id); });
    }

    function markAllRead(button, refresh, errorState) {
        if (!button || button.disabled) return Promise.resolve();
        button.disabled = true;
        return requestJson('/api/notifications/read-all', { method: 'POST' })
            .then(function () { return refresh(); })
            .catch(function (error) {
                var state = errorState || panelState;
                showState(state, error.message, true, function () { markAllRead(button, refresh, errorState); });
            })
            .finally(function () { button.disabled = false; });
    }

    function loadBadge() {
        return requestJson('/api/notifications').then(function (result) {
            setUnreadCount(result.response.headers.get('X-Unread-Count') || result.data.length);
        }).catch(function (error) {
            if (panel && !overlay.hidden) showState(panelState, error.message, true, loadPanel);
            console.error('Unable to refresh notification count.', error);
        });
    }

    function loadHistory(pageOverride) {
        if (!history) return Promise.resolve();
        var requestId = ++historyRequestId;
        var list = history.querySelector('[data-notification-list]');
        var state = history.querySelector('[data-notification-state]');
        var params = new URLSearchParams();
        var page = pageOverride || Number(history.dataset.page || 1);
        params.set('page', String(page));
        params.set('per_page', '20');
        params.set('category', history.dataset.category || 'all');
        params.set('status', history.dataset.status || 'all');
        var search = history.querySelector('[data-notification-search-input]');
        if (search && search.value.trim()) params.set('q', search.value.trim());
        showState(state, 'Loading notifications…', false);
        return requestJson('/api/notifications/history?' + params.toString()).then(function (result) {
            if (requestId !== historyRequestId) return;
            history.dataset.page = String(result.data.page);
            setUnreadCount(result.data.unread_count);
            renderNotifications(list, result.data.notifications, state);
            var summary = history.querySelector('[data-notification-summary]');
            if (summary) summary.textContent = result.data.total + (result.data.total === 1 ? ' notification' : ' notifications');
            var pageLabel = history.querySelector('[data-notification-page-label]');
            if (pageLabel) pageLabel.textContent = result.data.pages ? 'Page ' + result.data.page + ' of ' + result.data.pages : 'Page 0 of 0';
            var previous = history.querySelector('[data-notification-previous]');
            var next = history.querySelector('[data-notification-next]');
            if (previous) previous.disabled = result.data.page <= 1;
            if (next) next.disabled = result.data.page >= result.data.pages;
            var url = new URL(window.location.href);
            ['page', 'category', 'status', 'q'].forEach(function (key) { url.searchParams.delete(key); });
            url.searchParams.set('page', String(result.data.page));
            if (history.dataset.category !== 'all') url.searchParams.set('category', history.dataset.category);
            if (history.dataset.status !== 'all') url.searchParams.set('status', history.dataset.status);
            if (search && search.value.trim()) url.searchParams.set('q', search.value.trim());
            window.history.replaceState({}, '', url);
        }).catch(function (error) {
            if (requestId === historyRequestId) showState(state, error.message, true, function () { loadHistory(page); });
        });
    }

    triggers.forEach(function (trigger) {
        trigger.addEventListener('click', function () {
            if (overlay && !overlay.hidden) closePanel();
            else openPanel(trigger);
        });
    });

    if (overlay) {
        overlay.addEventListener('click', function (event) {
            if (event.target === overlay || event.target.closest('[data-notification-close]')) closePanel();
            var filter = event.target.closest('[data-notification-category]');
            if (filter) {
                panelCategory = categories.indexOf(filter.dataset.notificationCategory) >= 0 ? filter.dataset.notificationCategory : 'all';
                updateCategoryButtons(overlay, panelCategory);
                loadPanel();
            }
            var markAll = event.target.closest('[data-notification-mark-all]');
            if (markAll) markAllRead(markAll, loadPanel, panelState);
        });
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closePanel();
    });

    if (history) {
        var searchForm = history.querySelector('[data-notification-search]');
        if (searchForm) searchForm.addEventListener('submit', function (event) {
            event.preventDefault();
            history.dataset.page = '1';
            loadHistory(1);
        });
        history.querySelectorAll('[data-notification-status]').forEach(function (button) {
            button.addEventListener('click', function () {
                history.dataset.status = button.dataset.notificationStatus;
                history.dataset.page = '1';
                updateStatusButtons(history.querySelector('[data-notification-status-filters]'), history.dataset.status);
                loadHistory(1);
            });
        });
        history.querySelectorAll('[data-notification-category]').forEach(function (button) {
            button.addEventListener('click', function () {
                history.dataset.category = button.dataset.notificationCategory;
                history.dataset.page = '1';
                updateCategoryButtons(history.querySelector('[data-notification-category-filters]'), history.dataset.category);
                loadHistory(1);
            });
        });
        var markAllButton = history.querySelector('[data-notification-mark-all]');
        if (markAllButton) markAllButton.addEventListener('click', function (event) {
            markAllRead(
                event.currentTarget,
                function () { return loadHistory(Number(history.dataset.page || 1)); },
                history.querySelector('[data-notification-state]')
            );
        });
        var previousButton = history.querySelector('[data-notification-previous]');
        if (previousButton) previousButton.addEventListener('click', function () {
            loadHistory(Math.max(1, Number(history.dataset.page || 1) - 1));
        });
        var nextButton = history.querySelector('[data-notification-next]');
        if (nextButton) nextButton.addEventListener('click', function () {
            loadHistory(Number(history.dataset.page || 1) + 1);
        });
        var params = new URLSearchParams(window.location.search);
        var initialStatus = ['all', 'unread', 'read'].indexOf(params.get('status')) >= 0 ? params.get('status') : 'all';
        var initialCategory = categories.indexOf(params.get('category')) >= 0 ? params.get('category') : 'all';
        history.dataset.status = initialStatus;
        history.dataset.category = initialCategory;
        history.dataset.page = String(Math.max(1, Number(params.get('page')) || 1));
        var searchInput = history.querySelector('[data-notification-search-input]');
        if (searchInput) searchInput.value = params.get('q') || '';
        updateStatusButtons(history.querySelector('[data-notification-status-filters]'), initialStatus);
        updateCategoryButtons(history.querySelector('[data-notification-category-filters]'), initialCategory);
        loadHistory();
    } else if (triggers.length) {
        loadBadge();
        window.setInterval(loadBadge, 60000);
    }
})();
