function color = FCSFit_ChannelColor(fileName)

    % FCSFit_ChannelColor
    %
    % Colour of an FCSFit curve, chosen from the channels in its file name.
    % Returns [] when the name does not match, so FCSFit keeps its normal colour.
    %
    %   BB  blue          GG  green          RR  red
    %   BG  violet        BR  purple         GR  dark yellow
    %   BGR dark grey
    %
    % The channels are read from PAM's file names, '<file>_<PIE 1>_x_<PIE 2>.mcor':
    %   *_BB_x_BB, *_B_x_B, *_B1_x_B2   -> BB
    %   *_BB_x_GG, *_B_x_G, *_GG_x_BB   -> BG   (the order does not matter)
    %   *_BGR_x_BGR, *_BG_x_R           -> BGR
    % If the name has no '_x_' part, a stand-alone BB, GG, RR, BG, BR, GR or BGR
    % in the name is used instead (e.g. 'dsDNA_GR_run2').
    %
    % To change a colour, edit the RGB values (0..1) below.

    colors = struct( ...
        'BB',  [0    0    1   ], ...  % blue
        'GG',  [0    0.6  0   ], ...  % green
        'RR',  [1    0    0   ], ...  % red
        'BG',  [0.55 0.35 0.95], ...  % violet
        'BR',  [0.5  0    0.5 ], ...  % purple
        'GR',  [0.8  0.65 0   ], ...  % dark yellow
        'BGR', [0.2  0.2  0.2 ]);     % dark

    color = [];
    if isstring(fileName)
        fileName = char(fileName);
    end
    if ~ischar(fileName) || isempty(fileName)
        return;
    end
    fileName = regexprep(fileName, '\.(mcor|cor|pcor|fcs|dat|csv|txt)$', '', 'ignorecase');

    key = '';
    tok = regexp(fileName, '_([^_]+)_x_([^_]+)$', 'tokens', 'once');
    if ~isempty(tok)
        key = pairKey(tok{1}, tok{2});
    end
    if isempty(key)
        tok = regexp(fileName, '(?<![A-Za-z])([BGR]{2,3})(?![A-Za-z])', 'tokens');
        for k = numel(tok):-1:1 % the last match is usually the channel part
            letters = tok{k}{1};
            key = orderKey(letters);
            if numel(letters) == 2 && letters(1) == letters(2)
                key = letters;
            elseif numel(unique(letters)) ~= numel(letters)
                key = ''; % e.g. 'BBG' is not a channel name
            end
            if isfield(colors, key)
                break;
            end
        end
    end
    if ~isempty(key) && isfield(colors, key)
        color = colors.(key);
    end
end

function key = pairKey(a, b)
    % channel letters of the two PIE channels -> 'BB', 'BG', ..., 'BGR' or ''
    la = channelLetters(a);
    lb = channelLetters(b);
    if isempty(la) || isempty(lb)
        key = '';
        return;
    end
    key = orderKey([la lb]);
    if numel(key) == 1 % auto-correlation (or two detectors of one colour)
        key = [key key];
    end
end

function letters = channelLetters(name)
    % 'BB' -> 'B', 'B1' -> 'B', 'BGR' -> 'BGR'; '' if the name is not made of B/G/R
    name = upper(regexprep(name, '[^A-Za-z]', ''));
    if isempty(name) || any(~ismember(name, 'BGR'))
        letters = '';
    else
        letters = orderKey(name);
    end
end

function key = orderKey(letters)
    % unique letters in the order B, G, R ('GB' -> 'BG', 'RG' -> 'GR')
    key = 'BGR';
    key = key(ismember(key, upper(letters)));
end
