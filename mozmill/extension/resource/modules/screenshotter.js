/* ***** BEGIN LICENSE BLOCK *****
 *   Version: MPL 1.1/GPL 2.0/LGPL 2.1
 *
 * The contents of this file are subject to the Mozilla Public License Version
 * 1.1 (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 * http://www.mozilla.org/MPL/
 *
 * Software distributed under the License is distributed on an "AS IS" basis,
 * WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
 * for the specific language governing rights and limitations under the
 * License.
 *
 * The Original Code is mozmill.
 *
 * The Initial Developer of the Original Code is the Mozilla Foundation.
 * Portions created by the Initial Developer are Copyright (C) 2010
 * the Initial Developer. All Rights Reserved.
 *
 * Contributor(s):
 *   Andrew Sutherland <asutherland@asutherland.org>
 *
 * Alternatively, the contents of this file may be used under the terms of
 * either the GNU General Public License Version 2 or later (the "GPL"), or
 * the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
 * in which case the provisions of the GPL or the LGPL are applicable instead
 * of those above. If you wish to allow use of your version of this file only
 * under the terms of either the GPL or the LGPL, and not to allow others to
 * use your version of this file under the terms of the MPL, indicate your
 * decision by deleting the provisions above and replace them with the notice
 * and other provisions required by the GPL or the LGPL. If you do not delete
 * the provisions above, a recipient may use your version of this file under
 * the terms of any one of the MPL, the GPL or the LGPL.
 *
 * ***** END LICENSE BLOCK ***** */

const EXPORTED_SYMBOLS = ['screenshotToDataURL', 'screenshotToBase64'];

var MODULE_NAME = 'test-screenshotify';

var RELATIVE_ROOT = '../shared-modules';
var MODULE_REQUIRES = ['folder-display-helpers', 'window-helpers'];

var folder;

/**
 * Render the contents of a window to a data URL.  Every effort is made to
 * make the screenshot as real as possible, but currently this is all done using
 * canvas-based rendering which is not the same thing as a real screenshot.
 *
 * @param aWindow The window to render
 * @param [aOptions] An object containing additional rendering instructions,
 *     such as DOM nodes to outline.
 */
function screenshotToDataURL(aWindow, aOptions) {
  // -- render to canvas
  let win = aWindow;
  let doc = win.document;
  let canvas = doc.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
  let width = win.innerWidth;
  let height = win.innerHeight;

  canvas.style.width = width + "px";
  canvas.style.height = height + "px";
  canvas.width = width;
  canvas.height = height;
  let ctx = canvas.getContext("2d");
  ctx.drawWindow(win, 0, 0, width, height, "rgb(0,0,0)");

  // - find all the sub-windows and render them
  function isVisible(aElem) {
    if (aElem.hidden || aElem.collapsed)
      return false;
    let parent = aElem.parentNode;
    if (parent == null)
      return true;
    if (("selectedPanel" in parent) &&
        parent.selectedPanel != aElem)
      return false;
    return isVisible(parent);
  }

  function subrenderCandidates(aElements) {
    for (let i = 0; i < aElements.length; i++) {
      let elem = aElements[i];
      if (isVisible(elem)) {
        let rect = elem.getBoundingClientRect();
        ctx.save();
        ctx.translate(rect.left, rect.top);
        ctx.drawWindow(elem.contentWindow,
                       0, 0,
                       rect.right - rect.left, rect.bottom - rect.top,
                       "rgb(255,255,255)");
        ctx.restore();
      }
    }
  }
  subrenderCandidates(doc.documentElement.getElementsByTagName("iframe"));
  subrenderCandidates(doc.documentElement.getElementsByTagName("browser"));

  return canvas.toDataURL("image/png", "");
}

/**
 * Render the contents of a window to a base64-encoded png file.
 */
function screenshotToBase64(aWindow, aOptions) {
  let dataUrl = screenshotToDataURL(aWindow, aOptions);
  return dataUrl.substring(dataUrl.indexOf("base64,") + 7);
}
