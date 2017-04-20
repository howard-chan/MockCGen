#!/usr/bin/python
"""
The MIT License (MIT)

Copyright (c) 2017 Howard Chan
https://github.com/howard-chan/MockCGen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import re
import sys
import argparse

# For Debug
import logging
import traceback

#TODO:
# Add Strong List (i.e. no WEAK attribute)
#

class MockCGen:
    '''
    @brief      Generates Interface Class and Fake Stubs:

    @details    Part 1: Build function list by parsing C headers
                Part 2: Generate pure virtual class header and fakes source
                files
    '''
    #====RE objects for parsing header files====
    #----RE match for <return type> <func name> (<arguments>);----
    # e.g.          "void          reset      (bool bTrue);"
    pattFunc = re.compile(r'^\s*?(?=\w)(.*?)(\w*?)\s*?\(([^;]*?)\)\s*;', re.MULTILINE)
    # Start of string       ^
    # Consume any space      \s*?
    # Lookahead for words        (?=\w)
    # Group1 (return type)             (.*?)
    # Group2 (func name)                    (\w*?)
    # Space between                               \s*?
    # Group3 (argument) anything but ";"              \(([^;]*?)
    # Closing statement                                         \)\s*;
    #----RE match for ..)..(..  pattern in arguments----
    # e.g.     "*fooCB)(bool bBar)"
    pattBadParenthesis = re.compile(r'^[^(]*(?=\))')
    # Start of string                 ^
    # Match any except '('             [^(]*
    # Before matching ')'                   (?=\))
    #----RE match for argument (i.e. last word in definition)----
    # e.g. volatile uint16_t **ppusValue))
    pattArg = re.compile(r'(\w+)(\[.*\])?$')
    # Match the word group (\w+)
    # Match 0 or 1 "[ ]"        (\[.*\])?
    # End of line                        $
    #----RE match for '...' in the arguments----
    # e.g.  printf(...)
    pattArgEllipsis = re.compile('\.{3}')
    #----RE match for function pointer in the arguments----
    # e.g. 'type (*func_ptr)(...)'
    pattArgPFunc = re.compile('(\w*)\)\s*?\(')
    # Search for a word        (\w*)
    # That is before ") ("          \)\s*?\(
    #----RE match for curly braces, but ignore extern "C"----
    # e.g. 'static inline int foo(void) { return 0; }'
    pattBrace = re.compile(r'(?<!"C" ){[^{}]*}')
    # Negative look behind   (?<!"C" )
    # Match open brace                {
    # Match any except brace           [^{}]*
    # Match close brace                      }
    #----RE match for comment----
    # e.g. '/* This is a comment */' or foo() // This is a comment
    pattComment = re.compile(r'(/[*](?:.|[\r\n])*?[*]/)|(//.*)')
    # Match open comment        /[*]
    # Match anything or <CR>/<LF>   (?:.|[\r\n])*?
    # Match close comment                         [*]/
    # Or match C++ style comment                       |(//.*)

    #====Objects for file generation====
    # Defining the message and file lists
    fileList = []
    fileDict = {}

    def __init__(self, weak):
        '''
        @brief      Constructs the object.

        @param      self  The object
        @param      weak  The compiler specific string for "weak" attribute
                          (e.g. __attribute__(weak))
        '''
        self.weak = weak

    def ParseHeader(self, fileName, header):
        '''
        @brief      Parses the header file to be used in GMOCK generation

        @details    Parses "C" headers ".h" and adds function declarations into
                    file List and Dictionary which shall be used to generate
                    GMOCK compatible files

        @param      self      The object
        @param      fileName  Name of file to parse
        @param      header    The header
        '''
        funcList = []
        # Step 1: Remove all comments
        header = self.pattComment.sub('', header)
        # Step 2: Recursively filter out braces "{}" found in header (e.g. inline functions)
        while self.pattBrace.findall(header):
            header = self.pattBrace.sub('', header)
        # Step 3: Parse the file for lines that match the function declaration
        match = self.pattFunc.findall(header)
        for func in match:
            # Step 4.1: Process the components of the matched function declaration
            returnField, funcField, argsField = func[0], func[1], func[2]
            # Check that the fields are valid (i.e. a bad match will have empty fields)
            if len(returnField.lstrip(' ')) == 0 or \
               len(funcField.lstrip(' ')) == 0 or \
               len(argsField.lstrip(' ')) == 0:
                continue
            # Check that there are no bad parenthesis (e.g. when the pattern gets fooled)
            elif self.pattBadParenthesis.search(argsField) or \
                 self.pattBadParenthesis.search(funcField):
                continue
            # Check if this is an inline function which can't be mocked
            elif "inline" in returnField:
               continue
            # Step 4.2: Remove extern specifier if any, since they aren't used in classes
            returnField = returnField.replace('extern','')
            # Step 4.3: Add new tuple to list
            funcList.append((returnField, funcField, argsField))
        # Step 5: Add to fileList and dictionary if functions were found
        if funcList:
            self.fileList.append(fileName)
            self.fileDict[fileName] = funcList

    def ParseArgs(self, args):
        '''
        @brief      Parses the function argument string to a list of argument
                    identifiers only. The argument type is removed

        @param      self  The object
        @param      args  The argument string

        @return     argument string that is passed to the callee, and number of
                    arguments.  If return is (None, 0), then arguments are not supported
        '''
        strList = []
        try:
            argList = args.split(',')
            for arg in argList:
                match1 = self.pattArgEllipsis.search(arg)
                match2 = self.pattArg.search(arg)
                match3 = self.pattArgPFunc.search(arg)
                if match1:
                    # GMock doesn't support ellipsis (...)
                    return None, 0
                elif match2:
                    # Retrieve the argument
                    arg = match2.group(1)
                    # If the argument is foo(void), then don't pass to callee
                    if arg != 'void':
                        strList.append(arg)
                elif match3:
                    # return the function pointer portion
                    strList.append(match3.group(1))
        except:
            logging.error(traceback.format_exc())
        # Return the comma separate string and number of arguments
        return ', '.join(strList), len(strList)

    def BuildMockCHeader(self, file, className, isGMethodReqd = False):
        '''
        @brief      Builds a mock c header.

        @param      self           The object
        @param      file           The file
        @param      className      The class name
        @param      isGMethodReqd  Indicates if generating GMOCK methods is required
        '''
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('//DO NOT MODIFY--This is an autogenerated file--DO NOT MODIFY//\n')
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('#ifndef __%s_H__\n' % className.upper())
        file.write('#define __%s_H__\n' % className.upper())
        file.write('\n')
        file.write('#include <gmock/gmock.h>\n')
        file.write('#include <gtest/gtest.h>\n')
        file.write('#include <stdint.h>\n')
        file.write('\n')
        file.write('extern "C"\n')
        file.write('{\n')
        file.write('\n')
        # Generate include files
        file.write('// Include header files that are mocked\n')
        for header in self.fileList:
            file.write('#include "%s"\n' % header)
        file.write('\n')
        # ----Generate the virtual class----
        file.write('// The virtual class\n')
        file.write('class I%s\n' % className)
        file.write('{\n')
        file.write('public:\n')
        file.write('    // Destructor required for gmock\n')
        file.write('    virtual ~I%s() { }\n' % className)
        for fileName in self.fileList:
            file.write('\n    // From %s\n' % fileName)
            # Add the virtual members
            funcList = self.fileDict[fileName]
            for func in funcList:
                returnField, funcField, argsField = func[0], func[1], func[2]
                # Write the virtual member
                argsStr, argsCnt = self.ParseArgs(argsField)
                if argsStr == None:
                    file.write('    // Not supported: virtual %s%s(%s) = 0;\n' % (returnField, funcField, argsField))
                else:
                    file.write('    virtual %s%s(%s) = 0;\n' % (returnField, funcField, argsField))
        file.write('};\n')
        file.write('\n')
        if isGMethodReqd:
            # ----Generate the GMOCK class----
            file.write('// The GMOCK class\n')
            file.write('class MockI%s : public I%s\n' % (className, className))
            file.write('{\n')
            file.write('public:\n')
            for fileName in self.fileList:
                file.write('\n    // From %s\n' % fileName)
                # Add the MOCK members
                funcList = self.fileDict[fileName]
                for func in funcList:
                    returnField, funcField, argsField = func[0], func[1], func[2]
                    # Write the MOCK_METHOD
                    argsStr, argsCnt = self.ParseArgs(argsField)
                    if argsStr == None:
                        file.write('    // Not Supported: MOCK_METHOD%d(%s,%s(%s));\n' % (argsCnt, funcField, returnField, argsField))
                    else:
                        file.write('    MOCK_METHOD%d(%s,%s(%s));\n' % (argsCnt, funcField, returnField, argsField))
            file.write('};\n')
            file.write('\n')
        else:
            # Add include for post generated GMock file
            file.write('// Generate the GMOCK methods file %s.hpp using the following command\n' % className)
            file.write('// and be sure that the file is in the search path.\n')
            file.write('// googlemock/scripts/generator/gmock_gen.py %s.h >> %s.hpp\n' % (className, className))
            file.write('#include "%s.hpp"\n' % className)
            file.write('\n')
        # Generate the Mock initializer declaration
        file.write('// This must be called before the "C" mock is used\n')
        file.write('void %s_init(MockI%s *px%s);\n\n' % (className, className, className))
        file.write('} // extern "C"\n')
        file.write('#endif // __%s_H__\n' % className.upper())

    def BuildMockCSource(self, file, className):
        '''
        @brief      Builds a mock c source.

        @param      self       The object
        @param      file       The file
        @param      className  The class name
        '''
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('//DO NOT MODIFY--This is an autogenerated file--DO NOT MODIFY//\n')
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('\n')
        file.write('#include <stdint.h>\n')
        file.write('#include "etypes.h"\n')
        file.write('#include "%s.h"\n' % className)
        file.write('\n')
        file.write('extern "C"\n')
        file.write('{\n')
        file.write('using namespace ::testing;\n\n')
        file.write('//=============================================================\n')
        # Set the WEAK macro to the compiler specific implementation
        file.write('// Define WEAK to the compiler specific "weak" attribute\n')
        file.write('#undef  WEAK\n');
        file.write('#define WEAK    %s\n' % self.weak);
        file.write('\n')
        # Create mock pointer and initializer
        file.write('// Define the singleton pointer to the mock implementation\n')
        file.write('static MockI%s _px%sDummy;\n' % (className, className))
        file.write('static MockI%s *_px%s = &_px%sDummy;\n' % (className, className, className))
        file.write('\n')
        file.write('// This must be called before the "C" mock is used\n')
        file.write('void %s_init(MockI%s *px%s)\n' % (className, className, className))
        file.write('{\n')
        file.write('    _px%s = px%s;\n' % (className, className))
        file.write('}\n')
        file.write('//=============================================================\n')
        file.write('\n')
        # Generate the fake functions
        for fileName in self.fileList:
            file.write('\n// From %s\n' % fileName)
            funcList = self.fileDict[fileName]
            for func in funcList:
                returnField, funcField, argsField = func[0], func[1], func[2]
                # Generate the arguments
                argsStr, argCnt = self.ParseArgs(argsField)
                if argsStr == None:
                    file.write("// This function declaration is not supported by gMock\n")
                    file.write('// WEAK %s%s(%s) { }\n\n' % (returnField, funcField, argsField))
                else:
                    file.write('WEAK %s%s(%s)\n' % (returnField, funcField, argsField))
                    file.write('{\n')
                    # Generate call string
                    callStr = '_px%s->%s(%s);\n' % (className, funcField, argsStr)
                    # Check if a return is required (i.e. not void or has pointer)
                    if func[0].find('void') < 0 or returnField.find('*') >= 0:
                        callStr = 'return ' + callStr
                    # Write out call string
                    file.write('    %s' % callStr)
                    file.write('}\n\n')
        file.write('} // extern "C"\n')

def main(args):
    # Process the command line arguments
    parser = argparse.ArgumentParser(description="Generates GMOCK files from 'C' header files")
    parser.add_argument('-g', '--gmethod', action="store_true", help="Generate GMOCK methods directly")
    parser.add_argument('-l', '--list', action="store", help="Build mock functions from file list")
    parser.add_argument('-m', '--mock', action="store", default="mock", help="Base name for class and files")
    parser.add_argument('-p', '--path', action="store", default="", help="Output path")
    parser.add_argument('-w', '--weak', action="store", default="__attribute__((weak))", help="Compiler specific weak attribute")
    parser.add_argument('srcHdr', nargs='*')
    args = parser.parse_args()

    # Check the source of the headers
    if (args.list):
        with open(args.list) as file:
            for filename in file:
                args.srcHdr.append(filename)
        file.closed

    # Process the srcHdr
    if args.srcHdr:
        print "\tGenerating Mocks:"
        # Build the mock list
        mcg = MockCGen(args.weak)
        for filename in args.srcHdr:
            with open(filename.strip('\n')) as f:
                print "\t\tProcessing %s" % filename.strip('\n')
                mcg.ParseHeader(filename, f.read())
            f.closed
        # Save the mock header file
        savename = args.path + args.mock + ".h"
        with open(savename, 'wb') as f:
            mcg.BuildMockCHeader(f, args.mock, args.gmethod)
            print '\tSaved to "%s"' % savename
        f.closed
        # Save the mock source file
        savename = args.path + args.mock + ".cpp"
        with open(savename, 'wb') as f:
            mcg.BuildMockCSource(f, args.mock)
            print '\tSaved to "%s"' % savename
        f.closed
    else:
        parser.print_usage()

if __name__ == '__main__':
    main(sys.argv[1:])
