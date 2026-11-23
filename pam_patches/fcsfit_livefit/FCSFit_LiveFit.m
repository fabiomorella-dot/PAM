function FCSFit_LiveFit(fig)

    % FCSFit_LiveFit
    %
    % Adds a "Fit" button, a "Live fit" switch and a "Stop" button next to the
    % fit table of an FCSFit window.
    %
    %   Fit       runs the normal FCSFit fit (same as Start... > ...Fit)
    %   Live fit  when ticked, FCSFit refits by itself as soon as you
    %               - change a value, a fix/global tick or an active file in the fit table,
    %               - change the fit borders [s] or "Use weights",
    %               - load or add correlation files, or load another fit model.
    %   Stop      stops a running fit (same as Stop.... > ...Fit)
    %
    %   FCSFit_LiveFit(fig)   add the controls to this FCSFit window
    %   FCSFit_LiveFit        add them to every open FCSFit window
    %
    % FCSFit calls this automatically once apply_fcsfit_livefit has been run.

    if nargin < 1 || isempty(fig)
        figs = findobj('Type', 'figure', 'Tag', 'FCSFit');
        for k = 1:numel(figs)
            FCSFit_LiveFit(figs(k));
        end
        return;
    end

    if isappdata(fig, 'LiveFit')
        return; % already added to this window
    end

    h = guidata(fig);
    if ~isstruct(h) || ~all(isfield(h, {'Fit_Table', 'Fit_Function_Panel', 'DoFit'}))
        warning('FCSFit_LiveFit:unsupported', ...
            'This FCSFit window has no fit table or fit menu that FCSFit_LiveFit recognises; no live fit added.');
        return;
    end

    % colours of the existing GUI
    back = h.Fit_Function_Panel.BackgroundColor;
    fore = h.Fit_Function_Panel.ForegroundColor;
    if isfield(h, 'Fit_Min') && isgraphics(h.Fit_Min)
        control = h.Fit_Min.BackgroundColor;
    else
        control = [0.9 0.9 0.9];
    end

    % make room on the right of the fit table
    h.Fit_Table.Units = 'normalized';
    pos = h.Fit_Table.Position;
    h.Fit_Table.Position = [pos(1) pos(2) max(pos(3) - 0.075, 0.5) pos(4)];

    state = struct();
    state.Busy = false;
    state.Pending = false;

    state.FitButton = uicontrol( ...
        'Parent', h.Fit_Function_Panel, ...
        'Tag', 'LiveFit_FitButton', ...
        'Style', 'pushbutton', ...
        'Units', 'normalized', ...
        'FontSize', 12, ...
        'FontWeight', 'bold', ...
        'BackgroundColor', control, ...
        'ForegroundColor', fore, ...
        'String', 'Fit', ...
        'Callback', @(~, ~) requestFit(fig), ...
        'Position', [0.93 0.68 0.065 0.28], ...
        'TooltipString', 'Fit now (same as Start... > ...Fit)');

    state.Live = uicontrol( ...
        'Parent', h.Fit_Function_Panel, ...
        'Tag', 'LiveFit_Checkbox', ...
        'Style', 'checkbox', ...
        'Units', 'normalized', ...
        'FontSize', 11, ...
        'BackgroundColor', back, ...
        'ForegroundColor', fore, ...
        'String', 'Live fit', ...
        'Value', 0, ...
        'Callback', @(src, ~) liveToggled(src, fig), ...
        'Position', [0.93 0.40 0.065 0.22], ...
        'TooltipString', sprintf(['Refit automatically when you change the fit table,\n' ...
                                  'the fit borders or weights, or load files or a model.']));

    if isfield(h, 'StopFit') && isgraphics(h.StopFit)
        state.StopButton = uicontrol( ...
            'Parent', h.Fit_Function_Panel, ...
            'Tag', 'LiveFit_StopButton', ...
            'Style', 'pushbutton', ...
            'Units', 'normalized', ...
            'FontSize', 12, ...
            'BackgroundColor', control, ...
            'ForegroundColor', fore, ...
            'String', 'Stop', ...
            'Callback', @(~, ~) stopFit(fig), ...
            'Position', [0.93 0.06 0.065 0.28], ...
            'TooltipString', 'Stop the running fit (same as Stop.... > ...Fit)');
    end

    setappdata(fig, 'LiveFit', state);

    % refit after these user actions (only while "Live fit" is ticked)
    wrapCallback(fig, h, 'Fit_Table', 'CellEditCallback');
    wrapCallback(fig, h, 'Fit_Min', 'Callback');
    wrapCallback(fig, h, 'Fit_Max', 'Callback');
    wrapCallback(fig, h, 'Fit_Weights', 'Callback');
    wrapCallback(fig, h, 'LoadCor', 'Callback');
    wrapCallback(fig, h, 'AddCor', 'Callback');
    wrapCallback(fig, h, 'LoadFit', 'Callback');
end

function wrapCallback(fig, h, field, prop)

    % Runs FCSFit's own callback first, then a live refit.

    if ~isfield(h, field) || ~isgraphics(h.(field))
        return;
    end
    obj = h.(field);
    original = obj.(prop);
    obj.(prop) = @(src, evt) liveCallback(src, evt, original, fig);
end

function liveCallback(src, evt, original, fig)

    runCallback(original, src, evt);
    if ~isvalid(fig) || ~isappdata(fig, 'LiveFit')
        return;
    end
    state = getappdata(fig, 'LiveFit');
    if state.Live.Value
        requestFit(fig);
    end
end

function liveToggled(src, fig)

    if src.Value
        requestFit(fig);
    end
end

function requestFit(fig)

    % Runs FCSFit's fit. Requests that arrive while a fit is running are
    % merged into one refit right after it, so edits are never lost and
    % fits never pile up.

    state = getappdata(fig, 'LiveFit');
    state.Pending = true;
    if state.Busy
        setappdata(fig, 'LiveFit', state);
        return;
    end
    state.Busy = true;
    setappdata(fig, 'LiveFit', state);
    state.FitButton.String = 'Fitting...';
    cleanup = onCleanup(@() fitFinished(fig)); %#ok<NASGU>

    while true
        state = getappdata(fig, 'LiveFit');
        if ~state.Pending
            break;
        end
        state.Pending = false;
        setappdata(fig, 'LiveFit', state);
        try
            h = guidata(fig);
            runCallback(h.DoFit.Callback, h.DoFit, []);
        catch err
            warning('FCSFit_LiveFit:fitFailed', 'Fit failed: %s', err.message);
            break;
        end
        if ~isvalid(fig)
            return;
        end
    end
end

function fitFinished(fig)

    if ~isvalid(fig) || ~isappdata(fig, 'LiveFit')
        return;
    end
    state = getappdata(fig, 'LiveFit');
    state.Busy = false;
    state.Pending = false;
    setappdata(fig, 'LiveFit', state);
    if isvalid(state.FitButton)
        state.FitButton.String = 'Fit';
    end
end

function stopFit(fig)

    state = getappdata(fig, 'LiveFit');
    state.Pending = false; % no refit after stopping
    setappdata(fig, 'LiveFit', state);
    h = guidata(fig);
    runCallback(h.StopFit.Callback, h.StopFit, []);
end

function runCallback(cb, src, evt)

    % Calls a uicontrol/uimenu callback the way MATLAB would.

    if isempty(cb)
        return;
    elseif isa(cb, 'function_handle')
        cb(src, evt);
    elseif iscell(cb)
        feval(cb{1}, src, evt, cb{2:end});
    elseif ischar(cb) || isstring(cb)
        evalin('base', char(cb));
    end
end
